from __future__ import annotations

import html
import os
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import requests

NAVER_NEWS_API_URL = "https://openapi.naver.com/v1/search/news.json"

DEFAULT_QUERIES = [
    "artist comeback tour contract controversy",
    "OTT cinema box office trend",
    "tourism inbound outbound demand aviation fuel surcharge cancellation",
    "casino hotel leisure policy demand M&A strategic partnership regulation",
    "earnings guidance consensus operating profit sales revenue disclosure filing IR quarterly annual report",
]


def _clean(text: str) -> str:
    stripped = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", html.unescape(stripped)).strip()


def _parse_pubdate(value: str) -> datetime:
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def fetch_naver_news(display: int = 20) -> list[dict[str, Any]]:
    client_id = os.getenv("NAVER_CLIENT_ID", "").strip()
    client_secret = os.getenv("NAVER_CLIENT_SECRET", "").strip()

    if not client_id or not client_secret:
        return []

    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
    }

    all_items: list[dict[str, Any]] = []
    for query in DEFAULT_QUERIES:
        params = {"query": query, "display": display, "sort": "date"}
        try:
            response = requests.get(NAVER_NEWS_API_URL, headers=headers, params=params, timeout=20)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException:
            continue

        for raw in data.get("items", []):
            title = _clean(raw.get("title", ""))
            summary = _clean(raw.get("description", ""))
            link = raw.get("originallink") or raw.get("link") or ""
            if not title or not link:
                continue
            all_items.append(
                {
                    "title": title,
                    "summary": summary,
                    "link": link,
                    "source": "Naver News",
                    "published_at": _parse_pubdate(raw.get("pubDate", "")),
                }
            )

    return all_items
