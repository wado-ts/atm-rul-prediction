"""
CSV data loader for local/testing runs.

It returns the same PidLogGroup shape as the Oracle data access path so the
pipeline can switch data sources without touching downstream orchestration.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.config import get_settings
from app.models import MonetaryLogRecord, PidLogGroup

_COLUMNS = [
    "PID",
    "QUERY_DATE",
    "VERSION",
    "INSTITUTION",
    "NBRE_CAS_1",
    "NBRE_CAS_2",
    "NBRE3",
    "NBRE_CAS_4",
    "CMD_CAS_1",
    "CMD_CAS_2",
    "CMD_CAS_3",
    "CMD_CAS_4",
    "RECE_PRINT",
]


def _parse_datetime(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is not None:
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _required_int(row: dict[str, str], column: str) -> int:
    value = row.get(column, "").strip()
    if value == "":
        raise ValueError(f"CSV column {column} is required but was empty")
    return int(value)


def _optional_int(row: dict[str, str], column: str) -> int | None:
    value = row.get(column, "").strip()
    if value == "":
        return None
    return int(value)


def _optional_str(row: dict[str, str], column: str) -> str | None:
    value = row.get(column, "").strip()
    return value or None


def _record_from_row(row: dict[str, str]) -> MonetaryLogRecord:
    pid = row["PID"].strip()
    if not pid:
        raise ValueError("CSV column PID is required but was empty")

    return MonetaryLogRecord(
        pid=pid,
        query_date=_parse_datetime(row["QUERY_DATE"]),
        version=_required_int(row, "VERSION"),
        institution=_optional_str(row, "INSTITUTION"),
        nbre_cas_1=_required_int(row, "NBRE_CAS_1"),
        nbre_cas_2=_required_int(row, "NBRE_CAS_2"),
        nbre3=_required_int(row, "NBRE3"),
        nbre_cas_4=_required_int(row, "NBRE_CAS_4"),
        cmd_cas_1=_optional_int(row, "CMD_CAS_1"),
        cmd_cas_2=_optional_int(row, "CMD_CAS_2"),
        cmd_cas_3=_optional_int(row, "CMD_CAS_3"),
        cmd_cas_4=_optional_int(row, "CMD_CAS_4"),
        rece_print=_optional_int(row, "RECE_PRINT"),
    )


def fetch_from_csv_grouped_by_pid(lookback_days: int | None = None) -> list[PidLogGroup]:
    """Fetch recent monetary data from CSV, sorted and grouped by PID."""
    settings = get_settings()
    days = lookback_days if lookback_days is not None else settings.lookback_days
    window_start = datetime.utcnow() - timedelta(days=days)

    csv_path = Path(settings.csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    grouped: dict[str, list[MonetaryLogRecord]] = defaultdict(list)
    with csv_path.open(newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file)
        if reader.fieldnames is None:
            raise ValueError(f"CSV file has no header row: {csv_path}")

        missing = set(_COLUMNS) - set(reader.fieldnames)
        if missing:
            missing_columns = ", ".join(sorted(missing))
            raise ValueError(f"CSV missing required columns: {missing_columns}")

        records: list[MonetaryLogRecord] = []
        for row in reader:
            record = _record_from_row(row)
            if record.query_date >= window_start:
                records.append(record)

    records.sort(key=lambda record: (record.pid, record.query_date))
    for record in records:
        grouped[record.pid].append(record)

    return [PidLogGroup(pid=pid, records=records) for pid, records in grouped.items()]
