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


@pytest.mark.parametrize(
    "unit",
    ["token", "token.", "token-", "password", "secret_", "a.authorization-"],
)
@pytest.mark.parametrize("size", [8_000, 20_000, 32_768])
def test_masking_is_linear_on_adversarial_input(unit, size):
    """A long keyword run with no separator (the access-log ReDoS) masks in well under 100 ms,
    at the full size (no cut: `limit` is the text's length; 32 KiB is the traceback cap)."""
    import time

    text = "GET /api/v2/health?" + unit * (size // len(unit)) + " HTTP/1.1"
    start = time.perf_counter()
    mlog.mask_secrets(text, limit=len(text))
    assert time.perf_counter() - start < 0.1


@pytest.mark.parametrize(
    "text",
    [
        ("token" * 20 + "=" + " " * 30) * 400,
        "a=b" * 6000,
        "a://b:" * 3000,
        "token=a" * 2500,
        "token: Bearer " * 1500,
        ":" * 20_000,
        ("x" * 200 + "_token=v ") * 100,
    ],
    ids=["spaces", "chain", "urls", "secrets", "bearer", "colons", "long-keys"],
)
def test_masking_handles_many_separators_quickly(text):
    import time

    start = time.perf_counter()
    mlog.mask_secrets(text, limit=len(text))  # the whole text, not the 8 KiB cut
    assert time.perf_counter() - start < 0.1


@pytest.mark.parametrize(
    "message,secret",
    [
        ("a=password=hunter2", "hunter2"),
        ("headers: authorization=Bearer xyz987", "xyz987"),
        ("x" * 100 + "_token=abcabc", "abcabc"),
        ("q?id=1&access_token=t0k3n&z=2", "t0k3n"),
        ("set my.secret.key = 'quoted1'", "quoted1"),
    ],
)
def test_more_secret_shapes_are_masked(message, secret):
    assert secret not in mlog.mask_secrets(message)


def test_long_messages_are_cut_before_masking(lines):
    logging.getLogger("marcus.x").info("x" * 50_000)
    (line,) = lines()
    assert len(line["msg"]) <= mlog.MAX_MESSAGE_CHARS + 20


def test_access_log_line_is_cut_short(lines):
    logging.getLogger("uvicorn.access").info(
        '%s - "%s %s HTTP/%s" %d', "1.2.3.4:5", "GET", "/x?" + "a" * 9000, "1.1", 404
    )
    (line,) = lines()
    assert len(line["msg"]) <= mlog.MAX_ACCESS_CHARS + 20


SECRET = "Zq9Wv7Ky3Jp"
SECRET_SHAPES = [
    f"postgresql://marcus:{SECRET}@db:5432/marcus",
    f"password={SECRET}",
    f"Authorization: Bearer {SECRET}",
    f"cookie: marcus_owner={SECRET}; b=2",
    f'{{"client_secret": "{SECRET}"}}',
]


@pytest.mark.parametrize("shape", SECRET_SHAPES)
def test_a_cut_never_leaves_part_of_a_secret(shape):
    """Whatever character of the secret the cut lands on, no piece of it (2 chars or more)
    is left: the token the cut goes through is dropped, then the rest is masked."""
    at = shape.index(SECRET)
    limit = 200
    for k in range(len(shape) + 1):  # the cut lands k characters into the shape
        text = "x " * ((limit - k) // 2) + "y" * ((limit - k) % 2) + shape + " tail"
        assert text.index(shape) == limit - k
        out = mlog.mask_secrets(text, limit=limit)
        assert len(out) <= limit + len(mlog._CUT)
        pieces = {SECRET[i : i + 2] for i in range(len(SECRET) - 1)}
        assert not any(p in out for p in pieces), (k, at, out[-60:])
