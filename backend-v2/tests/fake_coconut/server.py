"""A fake COCONUT for the fake stack (docker-compose.fake.yml) and the e2e and judge runs.

It holds the name coconut.naturalproducts.net on the stack's internal network and answers on
443 with a certificate only the test CA (ca.pem) vouches for, so the production relay config in
docker/nginx.conf runs unchanged (fixed host, TLS verification, SNI) and nothing reaches the real
COCONUT. Standard library only (it runs in the api image as uid 10001, read-only root).

The three relayed calls, as COCONUT answers them:

- POST /api/auth/login {email, password}: LOGIN_EMAIL / LOGIN_PASSWORD get {access_token};
  "status-NNN@example.org" gets status NNN (any password); anything else 401.
- POST /api/reports/mutate with "Authorization: Bearer TOKEN": {created: [ids]}; more than
  MAX_ITEMS items: 422 about the list; "Bearer status-NNN": status NNN; any other or no
  token: 401.
- POST /api/search: SEARCH_DOI has SEARCH_ROWS rows (data.data); every other query none.

Anything else: 404. Every answer carries headers the relay must drop (EXTRA_HEADERS).

Each request is recorded in /tmp/seen.jsonl (method, path, query, headers, the TLS server name
the client asked for). Never a body; the Authorization value is recorded only as present or
not. The judge reads the file with `docker exec` to see what the relay sent upstream.
"""

from __future__ import annotations

import itertools
import json
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
SEEN = Path("/tmp/seen.jsonl")

LOGIN_EMAIL = "curator@example.org"
LOGIN_PASSWORD = "fake-coconut-password"  # noqa: S105 (a test fake's fixed login)
TOKEN = "fake-coconut-token"  # noqa: S105
SEARCH_DOI = "10.5555/marcus.fake.coconut"
SEARCH_ROWS = 3
MAX_ITEMS = 50

EXTRA_HEADERS = {
    "Set-Cookie": "laravel_session=fake; Path=/; HttpOnly",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Credentials": "true",
    "Content-Security-Policy": "default-src *",
    "X-Frame-Options": "ALLOWALL",
    "Strict-Transport-Security": "max-age=1",
    "Cache-Control": "public, max-age=3600",
    "Location": "https://example.org/elsewhere",
    "X-Powered-By": "fake-coconut",
    "X-Fake-Coconut": "1",
}

_ids = itertools.count(1001)
_lock = threading.Lock()


def _record(entry: dict) -> None:
    with _lock, SEEN.open("a") as f:
        f.write(json.dumps(entry) + "\n")


class Handler(BaseHTTPRequestHandler):
    server_version = "fake-coconut"
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        pass  # no access log: the record above is the only trace, and it has no secrets

    def _answer(self, status: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        for name, value in EXTRA_HEADERS.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(data)

    def _handle(self) -> None:
        url = urlsplit(self.path)
        headers = {k.lower(): v for k, v in self.headers.items()}
        auth = headers.pop("authorization", None)
        length = int(headers.get("content-length") or 0)
        raw = self.rfile.read(length) if length else b""
        _record(
            {
                "method": self.command,
                "path": url.path,
                "query": url.query,
                "headers": headers,
                "authorization": auth is not None,
                "sni": getattr(self.connection, "marcus_sni", None),
            }
        )
        try:
            body = json.loads(raw) if raw else {}
        except ValueError:
            return self._answer(400, {"message": "fake coconut: not JSON"})
        if not isinstance(body, dict):
            body = {}

        if self.command != "POST":
            return self._answer(405, {"message": "fake coconut: POST only"})
        if url.path == "/api/auth/login":
            email = str(body.get("email", ""))
            if email.startswith("status-") and email.endswith("@example.org"):
                code = int(email[len("status-") : -len("@example.org")])
                return self._answer(code, {"message": f"fake coconut {code}"})
            if email == LOGIN_EMAIL and body.get("password") == LOGIN_PASSWORD:
                return self._answer(200, {"access_token": TOKEN, "token_type": "Bearer"})
            return self._answer(401, {"message": "Invalid credentials"})
        if url.path == "/api/reports/mutate":
            if auth and auth.startswith("Bearer status-") and auth[14:].isdigit():
                code = int(auth[14:])
                return self._answer(code, {"message": f"fake coconut {code}"})
            if auth != f"Bearer {TOKEN}":
                return self._answer(401, {"message": "Unauthenticated."})
            items = body.get("mutate")
            if not isinstance(items, list):
                return self._answer(422, {"message": "The mutate field is required."})
            if len(items) > MAX_ITEMS:
                msg = f"The mutate field must not have more than {MAX_ITEMS} items."
                return self._answer(422, {"message": msg, "errors": {"mutate": [msg]}})
            with _lock:
                created = [next(_ids) for _ in items]
            return self._answer(200, {"created": created})
        if url.path == "/api/search":
            n = SEARCH_ROWS if body.get("query") == SEARCH_DOI else 0
            rows = [{"identifier": f"CNP{i:07d}"} for i in range(1, n + 1)]
            return self._answer(200, {"data": {"data": rows}})
        return self._answer(404, {"message": "fake coconut: not found"})

    # http.server dispatches on these names
    do_POST = do_GET = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = _handle  # noqa: N815


def main() -> None:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(HERE / "cert.pem", HERE / "key.pem")

    def keep_sni(sock, name, _ctx):  # the name the client asked for (SNI), or None
        sock.marcus_sni = name

    ctx.sni_callback = keep_sni
    server = ThreadingHTTPServer(("0.0.0.0", 443), Handler)  # noqa: S104 (internal network only)
    server.socket = ctx.wrap_socket(server.socket, server_side=True)
    print("fake coconut: https on 443", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
