from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


@dataclass
class UpdateLogRow:
    mineral: str
    month: str
    source_label: str
    source_unit: str
    value: str
    target_cell: str
    workbook_file: str
    status: str
    note: str


@dataclass
class ManualReviewRow:
    mineral: str
    month: str
    workbook_target: str
    issue_type: str
    note: str


UPDATE_COLUMNS = [
    "mineral",
    "month",
    "source_label",
    "source_unit",
    "value",
    "target_cell",
    "workbook_file",
    "status",
    "note",
]

MANUAL_COLUMNS = ["mineral", "month", "workbook_target", "issue_type", "note"]


def write_update_log(path: Path, rows: Iterable[UpdateLogRow]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=UPDATE_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def write_manual_review_log(path: Path, rows: Iterable[ManualReviewRow]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=MANUAL_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))
