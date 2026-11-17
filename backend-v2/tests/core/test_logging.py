"""JSON log lines: shape, request/paper/step context, secret masking."""

import json
import logging

import pytest

from marcus.core import logging as mlog


@pytest.fixture
def lines(monkeypatch):
    """Run configure_logging into a captured stream; yields a function returning parsed lines."""
    import io

    stream = io.StringIO()
    monkeypatch.setattr(mlog, "_stream", lambda: stream)
    root = logging.getLogger()
    saved = (root.handlers[:], root.level)
    mlog.configure_logging("testsvc")
    yield lambda: [json.loads(x) for x in stream.getvalue().splitlines() if x.strip()]
    root.handlers[:], root.level = saved


def test_line_has_the_fixed_fields(lines):
    logging.getLogger("marcus.x").warning("hello %s", "world")
    (line,) = lines()
    assert line["level"] == "WARNING"
    assert line["service"] == "testsvc"
    assert line["logger"] == "marcus.x"
    assert line["msg"] == "hello world"
    assert line["ts"].endswith("Z") and "T" in line["ts"]
    for absent in ("request_id", "paper_id", "step_id", "exc"):
        assert absent not in line


def test_context_ids_appear_only_while_bound(lines):
    log = logging.getLogger("marcus.x")
    with mlog.log_context(request_id="r1", paper_id="p1"):
        with mlog.log_context(step_id="s1"):
            log.info("inside")
        log.info("outer")
    log.info("after")
    inside, outer, after = lines()
    assert (inside["request_id"], inside["paper_id"], inside["step_id"]) == ("r1", "p1", "s1")
    assert "step_id" not in outer and outer["request_id"] == "r1"
    assert "request_id" not in after


def test_exception_goes_into_exc(lines):
    try:
        raise ValueError("boom")
    except ValueError:
        logging.getLogger("marcus.x").exception("failed")
    (line,) = lines()
    assert "ValueError: boom" in line["exc"]


@pytest.mark.parametrize(
    "message,secret",
    [
        ("login password=hunter2 ok", "hunter2"),
        ('{"token": "abc123def"}', "abc123def"),
        ("client_secret: s3cr3tvalue", "s3cr3tvalue"),
        ("Authorization: Bearer eyJhbGciOi.payload.sig", "eyJhbGciOi"),
        ("cookie: a=1; marcus_owner=OWNERTOKEN123; b=2", "OWNERTOKEN123"),
        ("connect redis://:redispw@redis:6379/0 failed", "redispw"),
        ("url /x?api_token=zzz999&b=1", "zzz999"),
    ],
)
def test_secrets_are_masked(lines, message, secret):
    logging.getLogger("marcus.x").info(message)
    (line,) = lines()
    assert secret not in json.dumps(line)
    assert "***" in line["msg"]


def test_secrets_in_args_and_exceptions_are_masked(lines):
    log = logging.getLogger("marcus.x")
    log.info("headers %s", {"authorization": "Bearer topsecretvalue"})
    try:
        raise RuntimeError("bad password=hunter2")
    except RuntimeError:
        log.exception("failed")
    for line in lines():
        assert "topsecretvalue" not in json.dumps(line)
        assert "hunter2" not in json.dumps(line)


def test_plain_text_is_untouched(lines):
    logging.getLogger("marcus.x").info("step 12 done in 3 ms; tokens are fine to mention")
    (line,) = lines()
    assert line["msg"] == "step 12 done in 3 ms; tokens are fine to mention"


def test_configure_is_idempotent(lines):
    mlog.configure_logging("testsvc")
    assert len(logging.getLogger().handlers) == 1
