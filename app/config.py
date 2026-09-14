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
    oracle_user: str
    oracle_password: str
    oracle_dsn: str
    # Connection pool sizing
    oracle_pool_min: int = 1
    oracle_pool_max: int = 4
    oracle_pool_increment: int = 1
    # Name of the table/view on the monetary server holding ATM cassette/dispense
    # snapshots. Expected columns (see database.py for the exact query):
    #   PID, QUERY_DATE, VERSION, INSTITUTION, NBRE_CAS_1, NBRE_CAS_2, NBRE3,
    #   NBRE_CAS_4, CMD_CAS_1, CMD_CAS_2, CMD_CAS_3, CMD_CAS_4, RECE_PRINT
    oracle_source_table: str
    # How many days back to pull on every run
    lookback_days: int = 60

    # ---- PostgreSQL (for auth/institutions) -------------------------------
    # DSN format expected by psycopg, e.g. "postgresql://user:pass@host:5432/db"
    postgres_dsn: str

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

    # ---- JWT / Auth ----------------------------------------------------------
    jwt_secret_key: str = "CHANGE_ME"
    jwt_algorithm: Literal["RS256", "HS256"] = "HS256"
    jwt_expiration_minutes: int = 60
    jwt_refresh_expiration_days: int = 30
    jwt_private_key_path: Optional[str] = None
    jwt_public_key_path: Optional[str] = None

    # ---- Internationalization (i18n) --------------------------------------
    default_language: str = "en"
    supported_languages: list[str] = ["en", "fr"]
    default_language_cookie: str = "i18n_lang"
    translation_dir: str = "locales"

    # ---- Institution sync ----------------------------------------------------
    institution_sync_enabled: bool = True
    institution_sync_interval_minutes: int = 60

    # ---- Pagination ----------------------------------------------------------
    default_page_size: int = 20
    max_page_size: int = 100
    allowed_page_sizes: list[int] = [10, 20, 50, 100]

    # ---- Search --------------------------------------------------------------
    search_debounce_ms: int = 300
    search_min_length: int = 1


@lru_cache
def get_settings() -> Settings:
    return Settings()
