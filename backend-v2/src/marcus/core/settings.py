from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MARCUS_", extra="ignore")

    database_url: str = "postgresql+asyncpg://marcus:marcus@postgres:5432/marcus"
    redis_url: str = "redis://redis:6379/0"
    data_root: Path = Path("/data")
    max_upload_bytes: int = 20 * 1024 * 1024
    max_pages: int = 100
    retention_days: int = 30
    browser_max_active_papers: int = 3
    ip_max_new_owners_per_hour: int = 10
    ip_max_active_papers: int = 6
    fair_window_s: int = 300
    trusted_proxies: list[str] = []
    enable_fake_engines: bool = False
    cookie_secure: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
