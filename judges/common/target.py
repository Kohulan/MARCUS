"""Pick the MARCUS base URL for a judge and refuse production hosts and ports."""
import os
from urllib.parse import urlparse

FORBIDDEN_HOSTS = {"marcus.decimer.ai", "api.marcus.decimer.ai", "jarvis.ian.uni-jena.de", "jarvis"}
# Production v1 on jarvis publishes 8080 (frontend) and 9000 (backend). Judges run ON jarvis (Task D4) against
# 127.0.0.1, and an SSH tunnel from another machine to those ports looks the same (a loopback URL), so these
# ports are refused on every loopback address, wherever the judge runs. Judge copies use 18080/19000/29000.
FORBIDDEN_LOOPBACK_PORTS = {8080, 9000}
_LOOPBACK_NAMES = {"localhost", "0.0.0.0", "::1", "::", "ip6-localhost"}

DEFAULT_BACKEND = "http://localhost:19000"
DEFAULT_FRONTEND = "http://localhost:18080"


def _is_loopback(host: str) -> bool:
    return host in _LOOPBACK_NAMES or host.startswith("127.") or host.endswith(".localhost")


def _check(url: str) -> str:
    u = urlparse(url)
    host = (u.hostname or "").lower()
    if host in FORBIDDEN_HOSTS or host.endswith(".uni-jena.de"):
        raise SystemExit(f"Refusing to run a judge against production host {host!r}.")
    try:
        port = u.port or (443 if u.scheme == "https" else 80)
    except ValueError:
        raise SystemExit(f"Refusing a judge URL with an invalid port: {url!r}.") from None
    if port in FORBIDDEN_LOOPBACK_PORTS and _is_loopback(host):
        raise SystemExit(f"Refusing to run a judge against {host}:{port}: ports 8080 and 9000 are production MARCUS "
                         f"on jarvis (also through an SSH tunnel). Use the judge copies (18080, 19000, 29000) or "
                         f"the v2 test stack (18090).")
    return url.rstrip("/")


def backend_url() -> str:
    return _check(os.environ.get("MARCUS_BACKEND_URL", DEFAULT_BACKEND))


def frontend_url() -> str:
    return _check(os.environ.get("MARCUS_FRONTEND_URL", DEFAULT_FRONTEND))
