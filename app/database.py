"""
Oracle DB access layer.

Responsible for exactly one thing: pulling the last `lookback_days` of raw
monetary-server snapshots out of Oracle and grouping the rows by PID (the
ATM identifier), so they can be handed to the sequence-building service.

Snapshots arrive roughly every 15 minutes per ATM. The 15-minute cadence is
NOT used as a filter or downsampling key - every row in the date window is
fetched and passed through as-is.

Uses python-oracledb (the modern, pure-python successor to cx_Oracle) in
"thin" mode, so no Oracle Instant Client install is required. Swap in
oracledb.init_oracle_client() if your DBA requires "thick" mode instead.

Wire up real access by setting these environment variables (see .env.example):
    ORACLE_USER, ORACLE_PASSWORD, ORACLE_DSN, ORACLE_SOURCE_TABLE
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta

import oracledb

from app.config import get_settings
from app.models import MonetaryLogRecord, PidLogGroup

logger = logging.getLogger(__name__)

_pool: oracledb.ConnectionPool | None = None

# Columns pulled from the monetary server, in the exact order the query
# selects them - adjust here (and in MonetaryLogRecord) if the schema changes.
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


def get_pool() -> oracledb.ConnectionPool:
    """Lazily create (and memoize) a connection pool to Oracle.

    A pool is used instead of a single connection so that the manual
    "run now" endpoint and the midnight scheduled job never contend for -
    or exhaust - a single connection.
    """
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = oracledb.create_pool(
            user=settings.oracle_user,
            password=settings.oracle_password,
            dsn=settings.oracle_dsn,
            min=settings.oracle_pool_min,
            max=settings.oracle_pool_max,
            increment=settings.oracle_pool_increment,
        )
        logger.info("Oracle connection pool created (dsn=%s)", settings.oracle_dsn)
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close(force=True)
        _pool = None
        logger.info("Oracle connection pool closed")


def _build_fetch_query(table: str) -> str:
    # Only QUERY_DATE is filtered on (the 30-day lookback window). No other
    # filters, and no aggregation/downsampling of the ~15-minute cadence -
    # every row in range is returned. Grouping by PID happens in Python
    # below; ORDER BY here just guarantees rows arrive pre-sorted per ATM.
    columns_sql = ",\n            ".join(_COLUMNS)
    return f"""
        SELECT
            {columns_sql}
        FROM {table}
        WHERE QUERY_DATE >= :window_start
        ORDER BY PID, QUERY_DATE
    """


def fetch_last_month_data_grouped_by_pid(
    lookback_days: int | None = None,
) -> list[PidLogGroup]:
    """Fetch the last `lookback_days` (default: settings.lookback_days) of
    monetary-server snapshots from the configured source and group by PID.

    Returns a list of PidLogGroup, one per distinct ATM seen in the window -
    exactly the shape the sequence-building service expects as input.
    """
    settings = get_settings()
    if settings.data_source == "csv":
        from app.csv_loader import fetch_from_csv_grouped_by_pid

        return fetch_from_csv_grouped_by_pid(lookback_days)

    days = lookback_days if lookback_days is not None else settings.lookback_days
    window_start = datetime.utcnow() - timedelta(days=days)

    query = _build_fetch_query(settings.oracle_source_table)

    grouped: dict[str, list[MonetaryLogRecord]] = defaultdict(list)

    try:
        pool = get_pool()
        with pool.acquire() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, window_start=window_start)
                columns = [col[0].lower() for col in cursor.description]
                for row in cursor:
                    row_dict = dict(zip(columns, row))
                    record = MonetaryLogRecord(
                        pid=str(row_dict["pid"]),
                        query_date=row_dict["query_date"],
                        version=row_dict.get("version"),
                        institution=row_dict.get("institution"),
                        nbre_cas_1=row_dict["nbre_cas_1"],
                        nbre_cas_2=row_dict["nbre_cas_2"],
                        nbre3=row_dict["nbre3"],
                        nbre_cas_4=row_dict["nbre_cas_4"],
                        cmd_cas_1=row_dict.get("cmd_cas_1"),
                        cmd_cas_2=row_dict.get("cmd_cas_2"),
                        cmd_cas_3=row_dict.get("cmd_cas_3"),
                        cmd_cas_4=row_dict.get("cmd_cas_4"),
                        rece_print=row_dict.get("rece_print"),
                    )
                    grouped[record.pid].append(record)
    except Exception as exc:
        logger.warning("Could not fetch data from Oracle DB (%s). Pipeline will fallback if appropriate.", exc)
        return []

    logger.info(
        "Fetched %d snapshot rows across %d ATMs (window_start=%s)",
        sum(len(v) for v in grouped.values()),
        len(grouped),
        window_start.isoformat(),
    )

    return [PidLogGroup(pid=pid, records=records) for pid, records in grouped.items()]
