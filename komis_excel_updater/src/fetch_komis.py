from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterable, Optional

import pandas as pd
import requests
from bs4 import BeautifulSoup

from utils import MineralConfig, normalize_text, parse_month, unit_matches

BASE_URL = "https://www.komis.or.kr/Komis/RsrcPrice/BaseMetals"


@dataclass(frozen=True)
class SeriesMeta:
    series_id: str
    mineral: str
    label: str
    unit: str


@dataclass(frozen=True)
class PriceRecord:
    mineral: str
    source_label: str
    source_unit: str
    month: date
    value: float


class KomisFetchError(RuntimeError):
    pass


class KomisClient:
    def __init__(self, timeout: int = 20):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) KOMIS-Excel-Updater/1.0",
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            }
        )

    def fetch_prices(self, mineral_configs: dict[str, MineralConfig]) -> tuple[list[PriceRecord], list[dict[str, str]]]:
        """
        Returns price records and issues for manual review.
        Issues format: {mineral, issue_type, note}
        """
        issues: list[dict[str, str]] = []
        series_meta = self._discover_series()

        selected: dict[str, SeriesMeta] = {}
        for mineral_name, cfg in mineral_configs.items():
            match, reason = select_best_series(series_meta, cfg)
            if match is None:
                issues.append(
                    {
                        "mineral": mineral_name,
                        "issue_type": reason,
                        "note": "해당 광종과 단위에 맞는 KOMIS 시계열을 자동 확정하지 못했습니다.",
                    }
                )
                continue
            selected[mineral_name] = match

        records: list[PriceRecord] = []
        for mineral_name, series in selected.items():
            points = self._fetch_monthly_by_series(series)
            if not points:
                issues.append(
                    {
                        "mineral": mineral_name,
                        "issue_type": "missing_series_data",
                        "note": f"선정된 시계열({series.label})에서 월평균 값을 찾지 못했습니다.",
                    }
                )
                continue
            for month, value in points:
                records.append(
                    PriceRecord(
                        mineral=mineral_name,
                        source_label=series.label,
                        source_unit=series.unit,
                        month=month,
                        value=value,
                    )
                )

        return records, issues

    def _discover_series(self) -> list[SeriesMeta]:
        resp = self.session.get(BASE_URL, timeout=self.timeout)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "lxml")

        # 1) Try explicit option tags
        series: list[SeriesMeta] = []
        for opt in soup.select("option"):
            value = (opt.get("value") or "").strip()
            label = opt.get_text(strip=True)
            if not value or not label:
                continue
            if len(value) < 2:
                continue
            unit = _extract_unit(label)
            series.append(
                SeriesMeta(
                    series_id=value,
                    mineral=label,
                    label=label,
                    unit=unit,
                )
            )

        # 2) Also inspect inline script JSON-like payloads
        if not series:
            series.extend(_extract_series_from_scripts(soup))

        # 3) Remove obviously bad duplicates
        unique: dict[tuple[str, str], SeriesMeta] = {}
        for row in series:
            key = (row.series_id, normalize_text(row.label))
            unique[key] = row

        discovered = list(unique.values())
        if not discovered:
            # Fallback: Playwright dynamic discovery
            discovered = self._discover_series_with_playwright()

        if not discovered:
            raise KomisFetchError("KOMIS 시계열 목록을 찾을 수 없습니다. 페이지 구조 변경 가능성이 있습니다.")

        return discovered

    def _discover_series_with_playwright(self) -> list[SeriesMeta]:
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            raise KomisFetchError("Playwright를 불러올 수 없어 동적 페이지 분석을 진행할 수 없습니다.") from exc

        series: list[SeriesMeta] = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(BASE_URL, wait_until="networkidle", timeout=60_000)
            html = page.content()
            browser.close()

        soup = BeautifulSoup(html, "lxml")
        for opt in soup.select("option"):
            value = (opt.get("value") or "").strip()
            label = opt.get_text(strip=True)
            if value and label and len(value) > 1:
                series.append(
                    SeriesMeta(series_id=value, mineral=label, label=label, unit=_extract_unit(label))
                )
        return series

    def _fetch_monthly_by_series(self, series: SeriesMeta) -> list[tuple[date, float]]:
        # API endpoint heuristics kept isolated for maintainability.
        candidates = [
            "https://www.komis.or.kr/Komis/Handler/RsrcPriceHandler.ashx",
            "https://www.komis.or.kr/Komis/RsrcPrice/GetBaseMetalsData",
            "https://www.komis.or.kr/Komis/RsrcPrice/GetChartData",
        ]

        payloads = [
            {"seriesId": series.series_id, "term": "M"},
            {"code": series.series_id, "period": "M"},
            {"item": series.series_id, "freq": "M"},
        ]

        for url in candidates:
            for payload in payloads:
                try:
                    resp = self.session.get(url, params=payload, timeout=self.timeout)
                    if resp.status_code >= 400:
                        continue
                    points = _parse_monthly_response(resp.text, series)
                    if points:
                        return points
                except Exception:
                    continue

        # last fallback: HTML table parsing from base page (if embedded)
        try:
            resp = self.session.get(BASE_URL, timeout=self.timeout)
            resp.raise_for_status()
            return _parse_html_tables_for_series(resp.text, series)
        except Exception:
            return []


def select_best_series(all_series: Iterable[SeriesMeta], cfg: MineralConfig) -> tuple[Optional[SeriesMeta], str]:
    candidates = []
    for item in all_series:
        label = normalize_text(item.label)
        if not any(k.lower() in label for k in cfg.series_keywords):
            continue
        if item.unit and not unit_matches(item.unit, cfg.expected_units):
            continue
        score = 0
        score += 10
        if cfg.strict_keywords and all(s.lower() in label for s in cfg.strict_keywords):
            score += 5
        if any(a.lower() in label for a in cfg.ambiguous_keywords):
            score -= 3
        candidates.append((score, item))

    if not candidates:
        return None, "skipped_missing_source"

    candidates.sort(key=lambda x: x[0], reverse=True)
    if len(candidates) > 1 and candidates[0][0] == candidates[1][0]:
        top_label_1 = normalize_text(candidates[0][1].label)
        top_label_2 = normalize_text(candidates[1][1].label)
        if top_label_1 != top_label_2:
            return None, "skipped_ambiguous_series"

    return candidates[0][1], "ok"


def _extract_unit(label: str) -> str:
    match = re.search(r"\(([^\)]+)\)", label)
    if match:
        return match.group(1).strip()

    lower = label.lower()
    if "usd" in lower and ("ton" in lower or "톤" in lower):
        return "USD/ton"
    if "cny" in lower and "kg" in lower:
        return "CNY/kg"
    if "만위안" in label and ("톤" in label or "ton" in lower):
        return "10k CNY/ton"
    return ""


def _extract_series_from_scripts(soup: BeautifulSoup) -> list[SeriesMeta]:
    results: list[SeriesMeta] = []
    for script in soup.find_all("script"):
        text = script.text or ""
        # attempt to find json arrays containing label/name and code/id
        matches = re.findall(r"(\[[\s\S]*?\])", text)
        for raw in matches:
            if "code" not in raw and "id" not in raw:
                continue
            try:
                arr = json.loads(raw)
            except Exception:
                continue
            if not isinstance(arr, list):
                continue
            for obj in arr:
                if not isinstance(obj, dict):
                    continue
                series_id = str(obj.get("code") or obj.get("id") or "").strip()
                label = str(obj.get("name") or obj.get("label") or "").strip()
                unit = str(obj.get("unit") or "").strip() or _extract_unit(label)
                if series_id and label:
                    results.append(SeriesMeta(series_id=series_id, mineral=label, label=label, unit=unit))
    return results


def _parse_monthly_response(text: str, series: SeriesMeta) -> list[tuple[date, float]]:
    try:
        data = json.loads(text)
        return _parse_monthly_from_json(data)
    except Exception:
        pass

    # pandas tolerant parse (csv-like)
    try:
        df = pd.read_csv(pd.io.common.StringIO(text))
        return _parse_monthly_from_dataframe(df)
    except Exception:
        pass

    return []


def _parse_monthly_from_json(data: Any) -> list[tuple[date, float]]:
    points: list[tuple[date, float]] = []

    def traverse(obj: Any) -> None:
        if isinstance(obj, dict):
            keys = {k.lower(): k for k in obj.keys()}
            date_key = keys.get("date") or keys.get("month") or keys.get("ym") or keys.get("yyyymm")
            value_key = keys.get("value") or keys.get("price") or keys.get("avg")
            if date_key and value_key:
                d = parse_month(obj.get(date_key))
                v = _to_float(obj.get(value_key))
                if d and v is not None:
                    points.append((d, v))
            for value in obj.values():
                traverse(value)
        elif isinstance(obj, list):
            for item in obj:
                traverse(item)

    traverse(data)

    unique = {(m, v) for m, v in points}
    return sorted(unique, key=lambda x: x[0])


def _parse_monthly_from_dataframe(df: pd.DataFrame) -> list[tuple[date, float]]:
    if df.empty:
        return []

    cols = {c.lower(): c for c in df.columns}
    date_col = cols.get("date") or cols.get("month") or cols.get("ym") or cols.get("yyyymm")
    value_col = cols.get("value") or cols.get("price") or cols.get("avg")
    if not date_col or not value_col:
        return []

    points: list[tuple[date, float]] = []
    for _, row in df.iterrows():
        d = parse_month(row[date_col])
        v = _to_float(row[value_col])
        if d and v is not None:
            points.append((d, v))
    return sorted({(m, v) for m, v in points}, key=lambda x: x[0])


def _parse_html_tables_for_series(html: str, series: SeriesMeta) -> list[tuple[date, float]]:
    dfs = pd.read_html(html)
    for df in dfs:
        points = _parse_monthly_from_dataframe(df)
        if points:
            return points
    return []


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None
