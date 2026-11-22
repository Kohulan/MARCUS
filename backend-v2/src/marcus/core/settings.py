import ipaddress
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from marcus.core.queues import SLOTS, TOOLS_QUEUE


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MARCUS_", extra="ignore")

    # No password here: every compose file sets MARCUS_DATABASE_URL with the real one.
    database_url: str = "postgresql+asyncpg://marcus@postgres:5432/marcus"
    redis_url: str = "redis://redis:6379/0"
    data_root: Path = Path("/data")
    max_upload_bytes: int = 20 * 1024 * 1024
    max_pages: int = 100
    # A page is rendered (300 DPI) only up to this many pixels; a larger one is final bad_input.
    # A4 is 8.7 MP; the cap stops a crafted page from writing a PNG of hundreds of MB.
    max_page_pixels: int = Field(50_000_000, gt=0)
    # And its PNG only up to this many bytes (an incompressible 50 MP page is ~150 MB; a text
    # page at 300 DPI is well under 5 MB); a larger one is final bad_input, nothing is written.
    max_page_png_bytes: int = Field(32 * 2**20, gt=0)
    # Below this many free bytes on data_root, POST /papers and POST /images answer 503 and
    # render_page writes nothing (retryable engine_error). The
    # Prometheus alert MarcusDiskUploadsRefused (ops/prometheus-alerts.yml) uses the same value.
    min_free_disk_bytes: int = Field(5 * 2**30, ge=0)
    retention_days: int = 30
    # The IP recorded when a browser first gets its key (owners.created_ip) is deleted this
    # many days after it was recorded (daily retention purge). The new-key limit needs 1 hour.
    # The privacy page (frontend-v2/src/pages/Privacy.tsx, pre-rendered) says "30 days":
    # change it with this value.
    owner_ip_retention_days: int = Field(30, gt=0)
    browser_max_active_papers: int = 3
    # New browser owners per client address per hour that were used (came back with their
    # cookie, or have a paper or image job). Owners never used again (the dropped cookies of a
    # new browser's parallel first requests) count only against ip_max_new_sessions_per_hour.
    ip_max_new_owners_per_hour: int = 10
    # Every owner row created per address per hour, used or not; default 10 x the limit above.
    ip_max_new_sessions_per_hour: int | None = Field(None, gt=0)
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
    # per client IP: GETs of page, crop and depiction images (marcus.api.security.ASSET_GET)
    rate_limit_ip_assets_per_min: int = 3000
    # per-call Redis timeout of the rate limiter (connect and read); a slower call is a failure
    # and 3 failures in 5 s open its breaker (marcus.api.security)
    rate_limit_redis_timeout_s: float = Field(1.0, gt=0)
    cors_origins: list[str] = []
    # HMAC key of the /tools/mcs highlight tokens (marcus.api.highlight). Unset: one random key
    # per deployment, kept in Redis. Never logged (SecretStr).
    highlight_key: SecretStr | None = Field(None, min_length=32)
    image_decode_concurrency: int = Field(2, gt=0)  # Pillow decodes at once, per API process
    expose_docs: bool = False
    log_level: str = "INFO"  # JSON logs (marcus.core.logging)
    # TensorFlow CPU thread pools in model workers, applied before the model loads
    # (marcus.workers.gpu.limit_tf_threads). Defaults = the compose defaults, so an image run
    # outside compose is capped too.
    tf_intra_threads: int = Field(4, gt=0)
    tf_inter_threads: int = Field(2, gt=0)
    # torch CPU threads in the torch OCSR workers, applied before the model loads
    # (marcus.workers.gpu.limit_torch_threads), inter-op threads = 1. Default = compose default.
    torch_threads: int = Field(4, gt=0)
    # MolScribe's torch device. v1 forces CPU; "cuda" only after a parity check on GPU.
    molscribe_device: Literal["cpu", "cuda"] = "cpu"
    # Segmenter version whose cached segmentation (seg_cache) new papers may reuse: the
    # pinned decimer_segmentation commit (compose sets it from docker/MODEL_PINS.md; the fake
    # stack sets the fake segmenter's version). Empty = never use the segmentation cache.
    seg_version: str = Field("", max_length=200)
    # Queues this deployment runs: GET /ready needs a live consumer on each. Comma list in env.
    expected_queues: Annotated[list[str], NoDecode] = []
    # Paper annotation with the local MARCUS model (marcus.workers.annotate, queue q.llm). The
    # API offers it only where a worker serves q.llm: docker-compose.gpu.yml (llama-server) and
    # docker-compose.fake.yml (the fake annotator) set it; elsewhere POST answers 503.
    annotate_enabled: bool = False
    # Worker side: "llama" = llama-server at annotator_url (internal network only); "fake" =
    # the fake annotator (refused unless enable_fake_engines).
    annotator: Literal["llama", "fake"] = "llama"
    annotator_url: str = Field("http://llama-server:8080", pattern=r"^https?://[^\s/]+(:\d+)?/?$")
    # One model request; below the annotate step's soft limit (120 s, marcus.core.queues).
    annotator_timeout_s: float = Field(110.0, gt=0)
    # Stored with every annotation; change them with the model file (docker-compose.gpu.yml).
    annotate_model: str = Field("qwen3.5-9b-marcus-v1", min_length=1, max_length=200)
    annotate_model_version: str = Field("Q8_0 llama.cpp b12554", min_length=1, max_length=200)
    rate_limit_annotate_per_min: int = 5  # per owner: POST /papers/{id}/annotation
    # An annotate or rgroups step older than this while no worker consumes q.llm (the model
    # service is down) fails as engine_error, so its paper is done again (dispatcher watchdog).
    annotate_max_wait_s: int = Field(600, gt=0)
    # per owner: PUT and DELETE /papers/{id}/annotation/curation (each save locates values)
    rate_limit_curation_per_min: int = 30
    # R-group definitions of a scaffold with the local R-group model (marcus.workers.rgroups,
    # queue q.llm, its own llama-server `llama-rgroup`). Offered by the API only where a worker
    # serves q.llm with that model: docker-compose.gpu.yml and docker-compose.fake.yml set it;
    # elsewhere POST answers 503.
    rgroup_enabled: bool = False
    # Worker side: "llama" = llama-server at rgroup_url (internal network only); "fake" = the
    # fake reader (refused unless enable_fake_engines).
    rgroup_reader: Literal["llama", "fake"] = "llama"
    rgroup_url: str = Field("http://llama-rgroup:8080", pattern=r"^https?://[^\s/]+(:\d+)?/?$")
    # One model request; below the rgroups step's soft limit (120 s, marcus.core.queues).
    rgroup_timeout_s: float = Field(110.0, gt=0)
    # Stored with every result; change them with the model file (docker-compose.gpu.yml).
    rgroup_model: str = Field("nuextract3-rgroup-v1", min_length=1, max_length=200)
    rgroup_model_version: str = Field("vision Q8_0 llama.cpp b12554", min_length=1, max_length=200)
    # per owner: POST /predictions/{id}/rgroups (a paper may have several scaffolds)
    rate_limit_rgroup_per_min: int = 20

    @model_validator(mode="after")
    def _sessions_default(self):
        if self.ip_max_new_sessions_per_hour is None:
            self.ip_max_new_sessions_per_hour = 10 * self.ip_max_new_owners_per_hour
        return self

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


def fake_enabled() -> bool:
    """The fake OCSR engine and fake segmenter may run (tests and the fake stack only). Every
    entry point refuses them otherwise: the API (deps.require_engine_enabled), the planner and
    the workers."""
    return get_settings().enable_fake_engines
