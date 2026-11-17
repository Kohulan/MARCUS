"""One JSON log format for api, dispatcher, workers and the metrics service.

`configure_logging(service)` replaces the root logger's handlers with one stderr handler that
writes a JSON object per line: ts, level, service, logger, msg, and (when bound) request_id,
paper_id, step_id, plus exc for a traceback. Ids come from contextvars: the security middleware
binds request_id (and paper_id from the URL), the worker runtime binds step_id and paper_id
around each step, via `log_context`.

Secrets never reach the output: a filter on the handler masks the value after any key or
parameter whose name contains password, token, secret or authorization, the `marcus_owner`
cookie, and the password part of `scheme://user:password@host` URLs (message and traceback).
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
_VALUE = r"""(?:(?:Bearer|Basic|Token)\s+)?[^\s,;&"'}\]]+"""
_SECRET_KEY = re.compile(
    rf"""(?P<key>[\w.-]*(?:password|token|secret|authorization)[\w.-]*|marcus_owner)"""
    rf"""(?P<sep>["']?\s*[:=]\s*["']?)(?P<val>{_VALUE})""",
    re.IGNORECASE,
)
_URL_PASSWORD = re.compile(r"(?P<head>://[^:/\s@]*:)[^@\s/]+(?=@)")


def mask_secrets(text: str) -> str:
    text = _SECRET_KEY.sub(lambda m: f"{m['key']}{m['sep']}{MASK}", text)
    return _URL_PASSWORD.sub(lambda m: f"{m['head']}{MASK}", text)


class MaskSecrets(logging.Filter):
    """Rewrites the record's message (args merged) and traceback text with secrets masked."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001  a bad format string must not lose the line
            message = f"{record.msg!r} {record.args!r}"
        record.msg, record.args = mask_secrets(message), None
        if record.exc_info:
            if not record.exc_text:
                record.exc_text = logging.Formatter().formatException(record.exc_info)
            record.exc_info = None
        if record.exc_text:
            record.exc_text = mask_secrets(record.exc_text)
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
            "msg": mask_secrets(record.getMessage()),  # no-op after MaskSecrets; belt and braces
        }
        for name, var in _context.items():
            value = var.get()
            if value:
                line[name] = value
        exc = record.exc_text
        if record.exc_info and not exc:
            exc = mask_secrets(self.formatException(record.exc_info))
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
_SERVER_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access", "gunicorn.error", "gunicorn.access")


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
