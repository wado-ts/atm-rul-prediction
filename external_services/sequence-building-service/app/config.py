from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Sequence Building Service"
    log_level: str = "INFO"

    # Artifact paths (configurable via env)
    artifacts_dir: str = "artifacts"
    scalers_dir: str = "scalers"
    categories_dir: str = "categories"
    categories_filename: str = "categories.json"

    @property
    def scalers_path(self) -> Path:
        return Path(self.artifacts_dir) / self.scalers_dir

    @property
    def categories_path(self) -> Path:
        return Path(self.artifacts_dir) / self.categories_dir / self.categories_filename


@lru_cache
def get_settings() -> Settings:
    return Settings()
