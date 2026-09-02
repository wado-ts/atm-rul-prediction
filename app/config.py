"""
Central configuration for the ATM Predictive Maintenance app.

Every external dependency (Oracle DB, sequence-building service, inference
service) is configured purely through environment variables so the same
code runs unchanged across dev/staging/prod. See .env.example for the full
list of variables and sane local defaults.
"""
from functools import lru_cache
from typing import Literal, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ---- General ---------------------------------------------------------
    app_name: str = "ATM Predictive Maintenance"
    environment: str = "development"

    # ---- Oracle DB (source-of-truth for ATM logs) -------------------------
    # DSN format expected by python-oracledb, e.g. "host:1521/service_name"
    oracle_user: str = "CHANGE_ME"
    oracle_password: str = "CHANGE_ME"
    oracle_dsn: str = "CHANGE_ME_HOST:1521/CHANGE_ME_SERVICE"
    # Connection pool sizing
    oracle_pool_min: int = 1
    oracle_pool_max: int = 4
    oracle_pool_increment: int = 1
    # Name of the table/view on the monetary server holding ATM cassette/dispense
    # snapshots. Expected columns (see database.py for the exact query):
    #   PID, QUERY_DATE, VERSION, INSTITUTION, NBRE_CAS_1, NBRE_CAS_2, NBRE3,
    #   NBRE_CAS_4, CMD_CAS_1, CMD_CAS_2, CMD_CAS_3, CMD_CAS_4, RECE_PRINT
    oracle_source_table: str = "CHANGE_ME_MONETARY_TABLE"
    # How many days back to pull on every run
    lookback_days: int = 30

    # ---- Data source --------------------------------------------------------
    # Use "csv" for local/testing runs that should bypass Oracle entirely.
    data_source: Literal["oracle", "csv"] = "oracle"
    csv_path: str = "data/monetary_data.csv"
    # Optional fixed reference time for testing (ISO format). If not set, uses datetime.utcnow()
    csv_reference_time: Optional[str] = None

    # ---- Component RUL / risk thresholds -----------------------------------
    # Applied per component: predicted_rul_days <= critical -> critical,
    # <= warning -> warning, else healthy. Only used when the inference
    # service returns a numeric predicted_rul_days for that component.
    rul_critical_threshold_days: float = 7.0
    rul_warning_threshold_days: float = 14.0

    # ---- Sequence-building service -----------------------------------------
    sequence_builder_url: str = "http://localhost:9001/build-sequences"
    sequence_builder_timeout_seconds: float = 30.0

    # ---- Inference service --------------------------------------------------
    inference_service_url: str = "http://localhost:9002/predict-rul"
    inference_service_timeout_seconds: float = 30.0

    # ---- Scheduler -----------------------------------------------------------
    # Daily automatic run time (24h clock, server timezone)
    daily_run_hour: int = 0
    daily_run_minute: int = 0


@lru_cache
def get_settings() -> Settings:
    return Settings()
