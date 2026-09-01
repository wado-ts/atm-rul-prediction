from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Inference Service"
    log_level: str = "INFO"

    # Directory holding each component's serialized trained model.
    trained_models_dir: str = "trained_models"
    deephit_model_pattern: str = "DynamicDeepHit_{component}.pt"
    bin

    # Risk thresholds (from main app config)
    rul_critical_threshold_days: float = 7.0
    rul_warning_threshold_days: float = 14.0


@lru_cache
def get_settings() -> Settings:
    return Settings()