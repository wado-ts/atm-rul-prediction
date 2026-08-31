from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Inference Service"
    log_level: str = "INFO"

    # Directory holding each component's serialized trained model.
    trained_models_dir: str = "trained_models"
    component_1_model_file: str = "component_1_coxph.pkl"
    component_2_model_file: str = "component_2_coxph.pkl"
    component_3_model_file: str = "component_3_coxph.pkl"
    component_4_model_file: str = "component_4_coxph.pkl"
    component_5_model_file: str = "component_5_coxph.pkl"


@lru_cache
def get_settings() -> Settings:
    return Settings()
