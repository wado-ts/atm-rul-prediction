"""
CSV data loader for local/testing runs.

It returns the same PidLogGroup shape as the Oracle data access path so the
pipeline can switch data sources without touching downstream orchestration.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import polars as pl

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

_INT_COLUMNS = [
    "VERSION",
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

_REQUIRED_COMPONENT_COLUMNS = [
    "CMD_CAS_1",
    "CMD_CAS_2",
    "CMD_CAS_3",
    "CMD_CAS_4",
]


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _get_reference_time(settings) -> datetime:
    """Get reference time for CSV filtering. Uses csv_reference_time if set, else utcnow."""
    if settings.csv_reference_time:
        return datetime.fromisoformat(settings.csv_reference_time)
    return datetime.utcnow()


def _scan_csv(csv_path: Path) -> pl.LazyFrame:
    return pl.scan_csv(
        csv_path,
        null_values=[""],
        schema_overrides={"PID": pl.Utf8, "QUERY_DATE": pl.Utf8, "INSTITUTION": pl.Utf8},
    )


def _validate_columns(lf: pl.LazyFrame) -> None:
    missing = set(_COLUMNS) - set(lf.collect_schema().names())
    if missing:
        missing_columns = ", ".join(sorted(missing))
        raise ValueError(f"CSV missing required columns: {missing_columns}")


def fetch_from_csv_grouped_by_pid(lookback_days: int | None = None) -> list[PidLogGroup]:
    """Fetch recent monetary data from CSV, sorted and grouped by PID."""
    settings = get_settings()
    days = lookback_days if lookback_days is not None else settings.lookback_days
    reference_time = _get_reference_time(settings)
    window_start = reference_time - timedelta(days=days)

    csv_path = Path(settings.csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    lf = _scan_csv(csv_path)
    _validate_columns(lf)

    parsed_lf = (
        lf.select(_COLUMNS)
        .with_columns(
            pl.col("QUERY_DATE").str.to_datetime(strict=False).alias("QUERY_DATE"),
            *[pl.col(column).cast(pl.Int64, strict=False) for column in _INT_COLUMNS],
        )
        .filter(pl.col("QUERY_DATE").is_not_null())
        .filter(pl.col("QUERY_DATE") >= pl.lit(window_start))
        .filter(
            (pl.col("CMD_CAS_1").is_null().sum().over("PID") == 0)
            & (pl.col("CMD_CAS_2").is_null().sum().over("PID") == 0)
            & (pl.col("CMD_CAS_3").is_null().sum().over("PID") == 0)
            & (pl.col("CMD_CAS_4").is_null().sum().over("PID") == 0)
        )
        .sort(["PID", "QUERY_DATE"])
    )

    df = parsed_lf.collect()

    grouped: dict[str, list[MonetaryLogRecord]] = defaultdict(list)
    for row in df.iter_rows(named=True):
        record = MonetaryLogRecord(
            pid=row["PID"],
            query_date=_normalize_datetime(row["QUERY_DATE"]),
            version=row["VERSION"],
            institution=row["INSTITUTION"],
            nbre_cas_1=row["NBRE_CAS_1"],
            nbre_cas_2=row["NBRE_CAS_2"],
            nbre3=row["NBRE3"],
            nbre_cas_4=row["NBRE_CAS_4"],
            cmd_cas_1=row["CMD_CAS_1"],
            cmd_cas_2=row["CMD_CAS_2"],
            cmd_cas_3=row["CMD_CAS_3"],
            cmd_cas_4=row["CMD_CAS_4"],
            rece_print=row["RECE_PRINT"],
        )
        grouped[record.pid].append(record)

    return [PidLogGroup(pid=pid, records=records) for pid, records in grouped.items()]
