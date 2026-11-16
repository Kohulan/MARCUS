"""End-to-end tests against the running local stack (nginx at 127.0.0.1:18090).

Start the stack with fake engines first:

    docker compose -p marcus-v2 -f docker-compose.yml -f docker-compose.fake.yml up -d --build

These tests talk HTTP only (httpx) and never import application code. The ready test also
uses the docker CLI to stop and restart one worker container. Without a reachable stack every
test is skipped with a message saying so.

Values mirror docker-compose.fake.yml: 2 fake segments per page, segmentation 2 s per page,
fake OCSR 1 s per segment.

Timing source: the API exposes no step timestamps, so the fairness numbers come from the
paper's server-sent events (arrival time on this host's clock) measured against the paper's
`created_at` from `GET /papers/{id}` (the stack runs on the same host, so one clock).
"""

import json
import math
import os
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

import httpx
import pytest

pytestmark = pytest.mark.e2e

BASE = os.environ.get("MARCUS_E2E_URL", "http://127.0.0.1:18090")
PROJECT = os.environ.get("MARCUS_E2E_PROJECT", "marcus-v2")
PDFS = Path(__file__).resolve().parent.parent / "fixtures" / "pdfs"
SEGMENTS_PER_PAGE = 2  # MARCUS_FAKE_SEGMENTS_PER_PAGE in docker-compose.fake.yml
READY_WAIT_S = int(os.environ.get("MARCUS_E2E_READY_WAIT_S", "240"))
UP_HINT = (
    "start it with: docker compose -p marcus-v2 -f docker-compose.yml "
    "-f docker-compose.fake.yml up -d --build"
)


# --- helpers -------------------------------------------------------------------------------


def _wait_ready(timeout_s: float) -> httpx.Response:
    deadline = time.monotonic() + timeout_s
    r = None
    while time.monotonic() < deadline:
        try:
            r = httpx.get(f"{BASE}/api/v2/ready", timeout=5)
            if r.status_code == 200:
                return r
        except httpx.HTTPError:
            pass
        time.sleep(1)
    return r


@pytest.fixture(scope="module", autouse=True)
def stack():
    try:
        httpx.get(f"{BASE}/api/v2/health", timeout=3)
    except httpx.HTTPError as exc:
        pytest.skip(f"MARCUS v2 stack not reachable at {BASE} ({type(exc).__name__}); {UP_HINT}")
    r = _wait_ready(READY_WAIT_S)
    assert r is not None and r.status_code == 200, (
        f"stack is up but not ready after {READY_WAIT_S} s: "
        f"{r.status_code if r is not None else 'no answer'} {r.text if r is not None else ''}"
    )


class Owner:
    """One browser owner: the cookie from the first response, sent by hand on every request
    (the stack may mark it Secure, which httpx would not send over plain http)."""

    def __init__(self) -> None:
        self.client = httpx.Client(base_url=BASE, timeout=30)
        r = self.client.get("/api/v2/papers")
        r.raise_for_status()
        raw = r.headers.get("set-cookie")
        assert raw, "first request of a new owner must set the owner cookie"
        self.client.cookies.clear()
        self.client.headers["Cookie"] = raw.split(";", 1)[0]

    def upload(self, name: str) -> tuple[str, float]:
        """Upload a fixture with the fake engine; (paper_id, client time before sending)."""
        data = (PDFS / name).read_bytes()
        sent = time.time()
        r = self.client.post(
            "/api/v2/papers",
            files={"file": (name, data, "application/pdf")},
            data={"engine": "fake"},
        )
        assert r.status_code == 202, r.text
        return r.json()["paper_id"], sent

    def paper(self, paper_id: str) -> dict:
        r = self.client.get(f"/api/v2/papers/{paper_id}")
        r.raise_for_status()
        return r.json()

    def wait_terminal(self, paper_id: str, timeout_s: float) -> dict:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            paper = self.paper(paper_id)
            if paper["status"] in ("done", "failed"):
                return paper
            time.sleep(1)
        raise AssertionError(f"paper {paper_id} not finished after {timeout_s} s: {paper}")

    def close(self) -> None:
        self.client.close()


def _created(paper: dict) -> float:
    return datetime.fromisoformat(paper["created_at"]).timestamp()


def _step_events(owner: Owner, paper_id: str, timeout_s: float):
    """Yield (arrival wall time, event dict) for each JSON `data:` line of the paper's SSE."""
    deadline = time.monotonic() + timeout_s
    with owner.client.stream(
        "GET", f"/api/v2/papers/{paper_id}/events", timeout=httpx.Timeout(30, read=30)
    ) as r:
        assert r.status_code == 200, r.read()
        assert r.headers["content-type"].startswith("text/event-stream")
        for line in r.iter_lines():
            if time.monotonic() > deadline:
                return
            if line.startswith("data:"):
                try:
                    event = json.loads(line[5:])
                except ValueError:
                    continue
                yield time.time(), event


def _docker_container(service: str) -> str | None:
    out = subprocess.run(
        [
            "docker", "ps", "-aq",
            "--filter", f"label=com.docker.compose.project={PROJECT}",
            "--filter", f"label=com.docker.compose.service={service}",
        ],
        capture_output=True, text=True, check=True,
    ).stdout.split()  # fmt: skip
    return out[0] if out else None


# --- tests ---------------------------------------------------------------------------------


def test_edge_headers_and_body_limit():
    r = httpx.get(f"{BASE}/api/v2/health", timeout=5)
    assert r.status_code == 200
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("x-frame-options") == "DENY"
    assert r.headers.get("referrer-policy") == "no-referrer"
    assert "frame-ancestors 'none'" in r.headers.get("content-security-policy", "")
    assert r.headers.get("x-request-id")
    # nginx is the edge: one copy of each header, and no version in Server
    assert len(r.headers.get_list("x-content-type-options")) == 1
    assert r.headers.get("server", "nginx") == "nginx"
    # 22 MB never reaches the API: nginx refuses it (client_max_body_size 21m)
    big = b"%PDF-1.4\n" + b"0" * (22 * 1024 * 1024)
    r = httpx.post(
        f"{BASE}/api/v2/papers", files={"file": ("big.pdf", big, "application/pdf")}, timeout=60
    )
    assert r.status_code == 413
    assert r.headers.get("x-content-type-options") == "nosniff"


def test_upload_to_done_with_fake_engines():
    owner = Owner()
    try:
        paper_id, _ = owner.upload("two_page.pdf")
        paper = owner.wait_terminal(paper_id, timeout_s=300)
        assert paper["status"] == "done", paper
        assert paper["pages"] == 2
        segments = paper["segments"]
        assert len(segments) == 2 * SEGMENTS_PER_PAGE
        assert sorted({s["page"] for s in segments}) == [0, 1]
        for seg in segments:
            assert seg["predictions"], f"segment {seg['id']} has no prediction"
            assert seg["predictions"][0]["engine"] == "fake"
        r = owner.client.get(f"/api/v2/segments/{segments[0]['id']}/image")
        assert r.status_code == 200 and r.content.startswith(b"\x89PNG")
    finally:
        owner.close()


def test_small_paper_starts_within_10s_behind_big_paper():
    a, b = Owner(), Owner()
    try:
        big_id, _ = a.upload("twenty_page.pdf")
        time.sleep(5)
        small_id, sent = b.upload("two_page.pdf")
        created = _created(b.paper(small_id))
        first_segment = first_prediction = a_pages_segmented = None
        for at, event in _step_events(b, small_id, timeout_s=90):
            if event.get("type") != "step":
                continue
            if (
                first_segment is None
                and event["kind"] == "segment_page"
                and (event["status"] == "running")
            ):
                first_segment = at
                # Contention check, right after B's start: a segment row exists only once its
                # page's segment_page step is done, so fewer than 20 pages here means A still
                # had segment_page work waiting while B's ran (the read comes after B started,
                # which only makes the check stricter).
                a_segs = a.client.get(f"/api/v2/papers/{big_id}/segments").json()["segments"]
                a_pages_segmented = len({s["page"] for s in a_segs})
            if event["kind"] == "ocsr" and event["status"] == "done":
                first_prediction = at
                break
        assert first_segment is not None, "no segment_page step of B started (SSE)"
        assert first_prediction is not None, "no prediction for B within 90 s (SSE)"
        big = a.paper(big_id)
        print(
            f"\nfairness (SSE arrival vs B.created_at): "
            f"B upload->created {created - sent:.2f} s, "
            f"first segment_page running {first_segment - created:.2f} s, "
            f"first prediction {first_prediction - created:.2f} s; "
            f"A pages segmented when B's first segment_page started: {a_pages_segmented}/20; "
            f"big paper status then: {big['status']}, steps {big['counts']['steps_by_status']}"
        )
        assert a_pages_segmented < 20, "A had no segment_page work left: no contention"
        assert big["status"] not in ("done", "failed"), "big paper finished first: no contention"
        assert first_segment - created < 10
        assert first_prediction - created < 60
        # B's prediction is really there
        segs = b.paper(small_id)["segments"]
        assert any(s["predictions"] for s in segs)
    finally:
        a.close()
        b.close()


def test_health_fast_during_load():
    owner = Owner()
    try:
        paper_id, _ = owner.upload("twenty_page.pdf")
        time.sleep(3)  # let the pipeline get going
        times = []
        with httpx.Client(base_url=BASE, timeout=5) as c:
            for _ in range(50):
                t0 = time.perf_counter()
                r = c.get("/api/v2/health")
                times.append(time.perf_counter() - t0)
                assert r.status_code == 200
        busy = owner.paper(paper_id)
        assert busy["status"] not in ("done", "failed"), "paper finished: not measured under load"
        p95 = sorted(times)[math.ceil(0.95 * len(times)) - 1]
        print(f"\nhealth under load: p95 {p95 * 1000:.1f} ms, max {max(times) * 1000:.1f} ms")
        assert p95 < 0.100
    finally:
        owner.close()


def test_ready_503_when_a_worker_is_stopped():
    if shutil.which("docker") is None:
        pytest.skip("docker CLI not available: cannot stop a worker")
    container = _docker_container("worker-fake-ocsr")
    if container is None:
        pytest.skip(f"no worker-fake-ocsr container in compose project {PROJECT}")
    assert httpx.get(f"{BASE}/api/v2/ready", timeout=5).status_code == 200
    subprocess.run(["docker", "stop", container], check=True, capture_output=True)
    try:
        deadline = time.monotonic() + 30
        r = None
        while time.monotonic() < deadline:
            r = httpx.get(f"{BASE}/api/v2/ready", timeout=5)
            if r.status_code == 503:
                break
            time.sleep(1)
        assert r is not None and r.status_code == 503, "ready stayed 200 with q.fake unserved"
        assert "queue:q.fake" in r.json()["missing"]
        assert all(m == "queue:q.fake" for m in r.json()["missing"]), r.json()
    finally:
        subprocess.run(["docker", "start", container], check=True, capture_output=True)
    r = _wait_ready(60)
    assert r is not None and r.status_code == 200, "ready did not recover after restart"
