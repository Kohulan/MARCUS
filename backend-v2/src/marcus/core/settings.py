import ipaddress
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
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
    sse_ping_interval_s: float = 15.0
    # fixed one-minute windows in Redis
    rate_limit_upload_per_min: int = 10  # per owner: POST /papers and POST /images together
    rate_limit_tools_per_min: int = 60  # per owner: every /tools/* call
    rate_limit_ip_per_min: int = 300  # per client IP: every route except GET /api/v2/health
    cors_origins: list[str] = []
    expose_docs: bool = False

    @field_validator("trusted_proxies")
    @classmethod
    def _proxies_are_networks(cls, value: list[str]) -> list[str]:
        """A typo here would silently trust nobody (or the wrong hop): refuse to start."""
        for entry in value:
            try:
                ipaddress.ip_network(entry.strip(), strict=False)
            except ValueError:
                raise ValueError(
                    f"trusted_proxies: {entry!r} is not an IP address or CIDR"
                ) from None
        return [entry.strip() for entry in value]


@lru_cache
def get_settings() -> Settings:
    return Settings()
