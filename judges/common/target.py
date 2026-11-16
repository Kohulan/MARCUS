"""Pick the MARCUS base URL for a judge and refuse production hosts."""
import os
from urllib.parse import urlparse

FORBIDDEN_HOSTS = {"marcus.decimer.ai", "api.marcus.decimer.ai", "jarvis.ian.uni-jena.de", "jarvis"}

DEFAULT_BACKEND = "http://localhost:19000"
DEFAULT_FRONTEND = "http://localhost:18080"


def _check(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if host in FORBIDDEN_HOSTS or host.endswith(".uni-jena.de"):
        raise SystemExit(f"Refusing to run a judge against production host {host!r}.")
    return url.rstrip("/")


def backend_url() -> str:
    return _check(os.environ.get("MARCUS_BACKEND_URL", DEFAULT_BACKEND))


def frontend_url() -> str:
    return _check(os.environ.get("MARCUS_FRONTEND_URL", DEFAULT_FRONTEND))
