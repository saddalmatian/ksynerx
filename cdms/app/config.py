from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "CDMS"
    environment: str = "dev"
    database_url: str = "postgresql+asyncpg://cdms:cdms@localhost:5432/cdms"
    emulator_base_url: str = "http://localhost:8080"
    poll_interval_seconds: int = 30
    webhook_secret: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
