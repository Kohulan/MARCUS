import ipaddress
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from marcus.core.queues import SLOTS, TOOLS_QUEUE


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
    sse_ping_interval_s: float = Field(15.0, gt=0)
    sse_max_streams_per_owner: int = Field(4, gt=0)
    sse_max_duration_s: float = Field(30 * 60, gt=0)  # then the client reconnects
    events_redis_max_connections: int = Field(200, gt=0)  # API pool: pub/sub + stream slots
    # fixed one-minute windows in Redis
    rate_limit_upload_per_min: int = 10  # per owner: POST /papers and POST /images together
    rate_limit_tools_per_min: int = 60  # per owner: every /tools/* call
    rate_limit_ip_per_min: int = 300  # per client IP: every route except GET /api/v2/health
    cors_origins: list[str] = []
    image_decode_concurrency: int = Field(2, gt=0)  # Pillow decodes at once, per API process
    expose_docs: bool = False
    # Queues this deployment runs: GET /ready needs a live consumer on each. Comma list in env.
    expected_queues: Annotated[list[str], NoDecode] = []

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

    @field_validator("expected_queues", mode="before")
    @classmethod
    def _queue_list(cls, value):
        """Comma list (env) or list; every name must be a known queue (a typo would make
        /ready wait for a queue nobody serves, or never check the real one)."""
        if isinstance(value, str):
            value = value.split(",")
        names = [str(v).strip() for v in value if str(v).strip()]
        known = {*SLOTS, TOOLS_QUEUE}
        unknown = [n for n in names if n not in known]
        if unknown:
            raise ValueError(f"expected_queues: unknown queue(s) {', '.join(unknown)}")
        return names

    @field_validator("cors_origins")
    @classmethod
    def _no_wildcard_origin(cls, value: list[str]) -> list[str]:
        """Credentials are allowed, so a wildcard would let any site act as the visitor."""
        if any(entry.strip() == "*" for entry in value):
            raise ValueError("cors_origins: '*' is not allowed; list each origin")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
