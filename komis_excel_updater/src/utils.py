from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, Optional

from dateutil import parser as date_parser


@dataclass(frozen=True)
class MineralConfig:
    mineral: str
    date_col: str
    price_col: str
    expected_units: list[str]
    series_keywords: list[str]
    strict_keywords: list[str]
    ambiguous_keywords: list[str]


@dataclass(frozen=True)
class WorkbookConfig:
    file_pattern: str
    fallback_search_patterns: list[str]
    sheet_name: str
    protected_sheet_names: list[str]
    output_name_template: str


@dataclass(frozen=True)
class LoggingConfig:
    update_log_name_template: str
    manual_review_log_name_template: str


@dataclass(frozen=True)
class AppConfig:
    workbook: WorkbookConfig
    logging: LoggingConfig
    minerals: dict[str, MineralConfig]


def load_config(config_path: Path) -> AppConfig:
    data = json.loads(config_path.read_text(encoding="utf-8"))
    workbook = WorkbookConfig(**data["workbook"])
    logging_cfg = LoggingConfig(**data["logging"])
    minerals: dict[str, MineralConfig] = {}
    for mineral, cfg in data["minerals"].items():
        minerals[mineral] = MineralConfig(mineral=mineral, **cfg)
    return AppConfig(workbook=workbook, logging=logging_cfg, minerals=minerals)


def ensure_directories(*paths: Path) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def now_timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def parse_month(value: Any) -> Optional[date]:
    if value is None:
        return None

    if isinstance(value, datetime):
        return date(value.year, value.month, 1)

    if isinstance(value, date):
        return date(value.year, value.month, 1)

    if isinstance(value, (int, float)):
        # Excel serial date (1900-based, openpyxl usually parses this already)
        try:
            parsed = datetime.fromordinal(datetime(1899, 12, 30).toordinal() + int(value))
            return date(parsed.year, parsed.month, 1)
        except Exception:
            return None

    text = str(value).strip()
    if not text:
        return None

    try:
        parsed = date_parser.parse(text, fuzzy=True)
        return date(parsed.year, parsed.month, 1)
    except Exception:
        return None


def canonicalize_unit(unit: str) -> str:
    return (
        unit.lower()
        .replace(" ", "")
        .replace("us$", "usd")
        .replace("/mt", "/ton")
        .replace("吨", "톤")
    )


def unit_matches(source_unit: str, expected_units: list[str]) -> bool:
    source = canonicalize_unit(source_unit)
    return any(canonicalize_unit(u) == source for u in expected_units)


def normalize_text(value: str) -> str:
    return " ".join(str(value).strip().lower().split())


def is_empty_cell(value: Any) -> bool:
    return value is None or str(value).strip() == ""


def choose_workbook_path(base_dir: Path, workbook_cfg: WorkbookConfig) -> Optional[Path]:
    primary = base_dir / workbook_cfg.file_pattern
    if primary.exists():
        return primary

    for pattern in workbook_cfg.fallback_search_patterns:
        for candidate in sorted(base_dir.glob(pattern)):
            if candidate.name.startswith("~$"):
                continue
            return candidate
    return None


def excel_cell(col: str, row: int) -> str:
    return f"{col}{row}"
