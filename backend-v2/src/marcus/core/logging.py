"""One JSON log format for api, dispatcher, workers and the metrics service.

`configure_logging(service)` replaces the root logger's handlers with one stderr handler that
writes a JSON object per line: ts, level, service, logger, msg, and (when bound) request_id,
paper_id, step_id, plus exc for a traceback. Ids come from contextvars: the security middleware
binds request_id (and paper_id from the URL), the worker runtime binds step_id and paper_id
around each step, via `log_context`.

Secrets never reach the output: a filter on the handler masks the value after any key or
parameter whose name contains password, token, secret or authorization, the `marcus_owner`
cookie, and the password part of `scheme://user:password@host` URLs (message and traceback).
Masking runs in linear time, on a message first cut to MAX_MESSAGE_CHARS (MAX_ACCESS_CHARS for
an access-log line, whose path and query the client chooses; 4x for a traceback).
"""

import contextlib
import contextvars
import json
import logging
import re
import sys
from collections.abc import Iterator
from datetime import UTC, datetime

CONTEXT_FIELDS = ("request_id", "paper_id", "step_id")
_context: dict[str, contextvars.ContextVar[str | None]] = {
    name: contextvars.ContextVar(f"log_{name}", default=None) for name in CONTEXT_FIELDS
}

MASK = "***"
MAX_MESSAGE_CHARS = 8 * 1024  # a log message (and a traceback, x4) is cut to this before masking
MAX_ACCESS_CHARS = 2 * 1024  # an access-log line: the client chooses its path and query
_ACCESS_LOGGERS = frozenset({"uvicorn.access", "gunicorn.access"})
_CUT = " …[cut]"
_VALUE = r"""(?:(?:Bearer|Basic|Token)\s+)?[^\s,;&"'}\]]+"""
# Linear time: a key starts only where a run of key characters starts (the lookbehind), so each
# run is walked once; the separator's spaces are bounded; the secret word is tested on the key
# afterwards (_SECRET_NAME), never inside the pattern.
_KEY_SEP = re.compile(
    r"""(?<![\w.-])(?P<key>[\w.-]+)["']?\s{0,16}[:=]\s{0,16}["']?(?=[^\s,;&"'}\]])"""
)
_SECRET_VALUE = re.compile(_VALUE, re.IGNORECASE)
_SECRET_NAME = re.compile(r"password|token|secret|authorization|marcus_owner", re.IGNORECASE)
_URL_PASSWORD = re.compile(r"(?P<head>://[^:/\s@]*:)[^@\s/]+(?=@)")


def _cut(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + _CUT


def _mask_keys(text: str) -> str:
    """The value after every key whose name holds a secret word, masked. A key without one is
    skipped only up to its separator, so its value is scanned again as a key itself (as in
    `a=password=x`); a value is read only after a secret key. Each search starts past the last
    one: linear overall."""
    out: list[str] = []
    pos = 0
    while (m := _KEY_SEP.search(text, pos)) is not None:
        out.append(text[pos : m.end()])
        pos = m.end()
        if _SECRET_NAME.search(m["key"]):
            value = _SECRET_VALUE.match(text, pos)
            if value is not None:
                out.append(MASK)
                pos = value.end()
    out.append(text[pos:])
    return "".join(out)


def mask_secrets(text: str, limit: int = MAX_MESSAGE_CHARS) -> str:
    """`text` cut to `limit` characters, then every secret in it masked."""
    text = _cut(text, limit)
    if ":" in text or "=" in text:
        text = _mask_keys(text)
    return _URL_PASSWORD.sub(lambda m: f"{m['head']}{MASK}", text)


class MaskSecrets(logging.Filter):
    """Rewrites the record's message (args merged) and traceback text with secrets masked."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001  a bad format string must not lose the line
            message = f"{record.msg!r} {record.args!r}"
        limit = MAX_ACCESS_CHARS if record.name in _ACCESS_LOGGERS else MAX_MESSAGE_CHARS
        record.msg, record.args = mask_secrets(message, limit), None
        if record.exc_info:
            if not record.exc_text:
                record.exc_text = logging.Formatter().formatException(record.exc_info)
            record.exc_info = None
        if record.exc_text:
            record.exc_text = mask_secrets(record.exc_text, 4 * MAX_MESSAGE_CHARS)
        return True


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str) -> None:
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, UTC)
        line = {
            "ts": ts.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": record.levelname,
            "service": self.service,
            "logger": record.name,
            # no-op after MaskSecrets (already cut and masked); belt and braces
            "msg": mask_secrets(record.getMessage(), MAX_MESSAGE_CHARS + len(_CUT)),
        }
        for name, var in _context.items():
            value = var.get()
            if value:
                line[name] = value
        exc = record.exc_text
        if record.exc_info and not exc:
            exc = mask_secrets(self.formatException(record.exc_info), 4 * MAX_MESSAGE_CHARS)
        if exc:
            line["exc"] = exc
        return json.dumps(line, ensure_ascii=False, default=str)


@contextlib.contextmanager
def log_context(**fields: object) -> Iterator[None]:
    """Bind request_id / paper_id / step_id for the current task or thread; restored on exit."""
    tokens = []
    for name, value in fields.items():
        if name not in _context:
            raise ValueError(f"unknown log field {name!r}")
        tokens.append((name, _context[name].set(None if value is None else str(value))))
    try:
        yield
    finally:
        for name, token in reversed(tokens):
            _context[name].reset(token)


def _stream():
    return sys.stderr


# Loggers that servers configure themselves (own handlers, no propagation): pull them in.
_SERVER_LOGGERS = (
    "uvicorn",
    "uvicorn.error",
    "uvicorn.access",
    "gunicorn.error",
    "gunicorn.access",
)


def configure_logging(service: str, level: str | None = None) -> None:
    """Install the JSON handler on the root logger (idempotent) for `service`."""
    if level is None:
        from marcus.core.settings import get_settings

        level = get_settings().log_level
    handler = logging.StreamHandler(_stream())
    handler.setFormatter(JsonFormatter(service))
    handler.addFilter(MaskSecrets())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    for name in _SERVER_LOGGERS:
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True
