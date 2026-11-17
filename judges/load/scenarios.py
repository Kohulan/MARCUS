"""Load and fairness scenarios S1-S5 for v1 and v2 (--client). Raw timings go to load/results/*.json.

    cd judges
    uv run python load/scenarios.py --target local  --scenarios S1 S4
    uv run python load/scenarios.py --target jarvis --scenarios S1 S2 S3 S4 S5      # GPU copy, guarded
    uv run python load/scenarios.py --target local  --client v2 --engine fake --scenarios S2 S3 S4 S5   # v2 fake stack
    uv run python load/scenarios.py --target jarvis --client v2 --base-url http://localhost:<tunnel> --scenarios S1 ...

Targets: local = the PRIVATE local copy http://localhost:19100 (load/docker-compose.local-private.yml; start it
first), jarvis = http://localhost:29000 through the SSH tunnel. Use --base-url to override.
On jarvis every scenario runs under guard_jarvis.Guard (production health + free GPU memory >= 3 GiB, before and
every 30 s); a trip stops the scenario at once and is written into its result file.

S1 baseline      one 15-structure paper alone, per engine: wall, segmentation, per-segment OCSR p50/p95.
S2 fairness      190-structure paper running; a 15-structure paper submitted 5 s later (--s2-small-count more
                 small papers each 10 s after the previous): small-paper wall, slowdown vs S1. S2_2020 = same
                 with the 2,020-structure paper as the big one. The big paper's OCSR is capped (--big-cap,
                 default 80 segments) to save GPU time; its segmentation is always complete.
S3 responsiveness /health and /session/heartbeat every 1 s while the 190-structure paper is segmented (and 15 s
                 idle before and after): latency p50/p95/max per probe kind (tests event-loop blocking).
S4 concurrency   two papers segmented at the same time vs one after the other (repeated): segments found,
                 lost pages, page errors from the backend log, error pages per batch of 4 (the backend
                 renders pages in a ThreadPool of 4 that shares one Keras model).
S5 script user   steady calls of /latest/ocsr/generate_smiles with an uploaded PNG, alone (--s5-seconds) and
                 during S2: latency p50/p95/max. Own rate-limit bucket (X-Session-ID) so the backend's
                 20 requests/min per client limit does not mix into the latency.

--client v2 (backend-v2, through nginx; the calls are mapped in load/v2_adapter.py): same scenarios, same result
fields, plus v2-only numbers. Result files are named <target>_v2_<scenario>_<time>.json.
  S1  same; the warm-up is one image job per engine (v2 workers preload their model at start).
  S2  the big paper runs FULL OCSR (--big-cap is ignored, with a log line): v2 has no reason to cap, and the spec
      gate is "while a 190-structure paper runs". Adds first_segment_start_s and first_smiles_s of each small paper
      (spec §3 Fair: < 10 s and < 60 s).
  S3  heartbeat = GET /api/v2/papers with the owner cookie; adds a depict probe (POST /api/v2/tools/depict every
      --depict-period-s; depict_p95_ms, spec §3 Responsive: < 2 s).
  S4  full pipeline (segmentation + OCSR) per paper (spec §3 Throughput: two at once faster than one after the
      other); page errors from failed page steps, not docker logs.
  S5  the script user is one image job per call (POST /api/v2/images, polled), on its own owner that is renewed
      before the per-owner upload limit; the depict probe also runs during the S2 part.
Each paper is its own owner (client_v2 starts without a cookie), as separate users would be. With --target
jarvis the guard always runs, also when --base-url points to another tunnel port. Every result records the host
load average (start/end) and, for v2, every HTTP answer >= 400 the adapter saw and the count of
503 "service unavailable" answers (the rate limiter's open circuit breaker).
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "goldset"))

import httpx  # noqa: E402

import make_fixtures  # noqa: E402
import v2_adapter  # noqa: E402
from common import client_v1, client_v2, remote, target  # noqa: E402
from common.client_v1 import run_paper  # noqa: E402
from guard_jarvis import Guard, GuardTripped, is_jarvis_url  # noqa: E402

RESULTS = HERE / "results"
TARGETS = {"local": "http://localhost:19100", "jarvis": "http://localhost:29000"}
TARGETS_V2 = {"local": "http://localhost:18090", "jarvis": "http://localhost:29090"}  # jarvis: pass --base-url
ENGINES = ["decimer", "molnextr", "molscribe"]
V2_ONLY_ENGINES = ["fake"]  # backend-v2 fake stack (MARCUS_ENABLE_FAKE_ENGINES=1) only
BIG_TIMEOUTS = dict(segment_timeout_s=3600, ocsr_timeout_s=900)  # long: we want to MEASURE the wait, not time out


# ------------------------------------------------------------------ small helpers
def pct(xs, q):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    k = (len(xs) - 1) * q / 100
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return round(xs[lo] + (xs[hi] - xs[lo]) * (k - lo), 1)


def stats(xs) -> dict:
    xs = [x for x in xs if x is not None]
    if not xs:
        return {"n": 0}
    return {"n": len(xs), "min": round(min(xs), 1), "p50": pct(xs, 50), "p95": pct(xs, 95), "max": round(max(xs), 1),
            "mean": round(sum(xs) / len(xs), 1)}


def utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def seg_stats(rec: dict) -> dict:
    ms = [s["ocsr_ms"] for s in rec["segments"] if s["ocsr_ms"] is not None]
    return {"n_segments": len(rec["segments"]), "n_errors": sum(1 for s in rec["segments"] if s["error"]),
            "n_fallback": sum(1 for s in rec["segments"] if s.get("fallback")), "ocsr_ms": stats(ms)}


def summarise_run(rec: dict, expected: int | None = None) -> dict:
    out = {"paper_id": rec["paper_id"], "engine": rec["engine"], "wall_ms": rec["wall_ms"], "segment_ms": rec["segment_ms"],
           "segments_reported": rec["segments_reported"], "segments_listed": rec["segments_listed"],
           "expected_structures": expected, "pages_total": rec["pages_total"], "pages_with_segments": rec["pages_with_segments"],
           "page_errors": rec["page_errors"], "fatal_error": rec["fatal_error"], "aborted": rec["aborted"], "backend_crash": rec.get("backend_crash"),
           "listed_pages": rec.get("listed_pages"), "http_calls": rec["http_calls"], "rate_limit_events": len(rec["rate_limit_events"]),
           "server_segment_s": rec.get("server_segment_s"), **seg_stats(rec)}
    if rec.get("client") == "client_v2":  # v2-only numbers (judges/README.md, "v1 vs v2 key meanings")
        out.update({"segment_compute_ms": rec.get("segment_compute_ms"), "ocsr_cache_hits": paper_cache_hits(rec),
                    "failed_steps": rec.get("failed_steps") or [], "cancelled": rec.get("cancelled"),
                    "ocsr_compute_ms": stats([s.get("ocsr_compute_ms") for s in rec["segments"]]),
                    "v2_paper_id": rec.get("v2_paper_id"), "events_mode": rec.get("events_mode"),
                    "timings_ms": rec.get("timings_ms"), **fairness_fields(rec)})
    return out


def paper_cache_hits(rec: dict) -> int:
    """OCSR cache hits of one v2 paper: the ``cached`` flag, or an engine time of 0 ms (worker images older than the
    flag never set it; the fake engine reports 1000 ms and never uses the cache)."""
    by_ms = sum(1 for s in rec.get("segments") or [] if s.get("cached") or s.get("ocsr_compute_ms") == 0)
    return max(rec.get("ocsr_cache_hits") or 0, by_ms)


def timing_validity(hits: int, failed_steps: list, allow_warm: bool) -> dict:
    """R21: a timed arm with an OCSR cache hit is not a cold timing; I2: nor is one whose docling / doi / check_pdf
    step failed (its wall is then a time limit). --allow-warm-cache accepts hits knowingly, never failed steps."""
    reasons = []
    if hits and not allow_warm:
        reasons.append(f"{hits} OCSR cache hit(s): not a cold timing (rerun on a cleared cache, or --allow-warm-cache)")
    bad = [f for f in failed_steps or [] if f.get("status") == "failed"]
    if bad:
        kinds = sorted({f["kind"] for f in bad})
        reasons.append(f"{len(bad)} failed non-page step(s) ({', '.join(kinds)}): the wall time is a time limit")
    out = {"valid": not reasons, "ocsr_cache_hits": hits, "failed_steps": len(bad), "reasons": reasons}
    if allow_warm:
        out["warm_cache_allowed"] = True
    return out


CACHE = None  # v2_adapter.CacheClear for the test stack (set by main), None = no clearing (v1 or --allow-warm-cache)
ALLOW_WARM = False


def cold(label: str) -> None:
    """Empty the test stack's OCSR cache before a timed scenario, arm or repeat (v2, R21)."""
    if CACHE is not None:
        CACHE.clear(label)


def fairness_fields(rec: dict) -> dict:
    """Seconds from upload to the paper's first segmentation step and to its first SMILES (spec §3 Fair).
    v2: from the steps (client_v2). v1 has no segmentation start; its first SMILES is the end of the first
    successful OCSR call (client clock)."""
    def s_(ms):
        return None if ms is None else round(ms / 1000, 1)

    if "first_segment_start_ms" in rec or "first_smiles_ms" in rec:
        return {"first_segment_start_s": s_(rec.get("first_segment_start_ms")), "first_smiles_s": s_(rec.get("first_smiles_ms")),
                "ocsr_done_s": s_(rec.get("ocsr_done_ms"))}
    ends = [s["t_start_ms"] + s["ocsr_ms"] for s in rec.get("segments") or []
            if not s.get("error") and s.get("t_start_ms") is not None and s.get("ocsr_ms") is not None]
    return {"first_segment_start_s": None, "first_smiles_s": s_(min(ends)) if ends else None,
            "ocsr_done_s": s_(rec.get("wall_ms"))}


def png_bytes(smiles="CN1C=NC2=C1C(=O)N(C(=O)N2C)C") -> bytes:
    from rdkit import Chem
    from rdkit.Chem import Draw

    img = Draw.MolToImage(Chem.MolFromSmiles(smiles), size=(400, 300))
    b = io.BytesIO()
    img.save(b, format="PNG")
    return b.getvalue()


def fixture(n: int) -> tuple[Path, dict]:
    return make_fixtures.ensure(n), make_fixtures.load_meta(n)


def lost_pages(rec: dict, meta: dict | list) -> list[int]:
    """Pages that contain fixture structures but yielded no segment file (uses the segment listing)."""
    per_page = meta["per_page"] if isinstance(meta, dict) else meta
    have = set(rec.get("listed_pages") or [])
    return sorted({i for i, n in enumerate(per_page) if n > 0} - have)


def server_ok(base_url: str, timeout=30) -> bool:
    try:
        return httpx.get(f"{base_url}/health", timeout=timeout).status_code == 200
    except Exception:
        return False


def create_session(base_url: str) -> str | None:
    try:
        r = httpx.post(f"{base_url}/session/create", timeout=30)
        return r.json()["session"]["session_id"]
    except Exception:
        return None


def remove_session(base_url: str, sid: str | None):
    if sid:
        try:
            httpx.delete(f"{base_url}/session/remove/{sid}", timeout=15)
        except Exception:
            pass


class Probe:
    """Fire a request at a fixed rate (open loop: probes overlap if the server is blocked) and record latency.

    mode="open": one request every ``period_s`` on its own thread, whether or not earlier ones returned
    (a browser setInterval does this).
    mode="closed": a script loop: call, wait for the answer, sleep ``period_s``, call again.
    """

    def __init__(self, name, make_call, period_s=1.0, mode="open", timeout_s=300.0, abort: threading.Event | None = None):
        self.name, self.make_call, self.period_s, self.mode, self.timeout_s = name, make_call, period_s, mode, timeout_s
        self.abort = abort  # a guard trip ends the probe at once (no new call is started)
        self.samples: list[dict] = []
        self._stop = threading.Event()
        self._thr: threading.Thread | None = None
        self._pool = ThreadPoolExecutor(max_workers=400, thread_name_prefix=f"probe-{name}")
        self._pending = []
        self.t0 = time.perf_counter()
        self._lock = threading.Lock()

    def _one(self):
        ts = time.perf_counter()
        status, err = None, None
        try:
            status = self.make_call(self.timeout_s)
        except Exception as e:
            err = f"{type(e).__name__}"
        ms = (time.perf_counter() - ts) * 1000
        with self._lock:
            self.samples.append({"t_ms": round((ts - self.t0) * 1000, 1), "ms": round(ms, 1), "status": status, "error": err})

    def _loop(self):
        nxt = time.perf_counter()
        while not self._stop.is_set() and not (self.abort is not None and self.abort.is_set()):
            if self.mode == "open":
                self._pending.append(self._pool.submit(self._one))
                nxt += self.period_s
                self._stop.wait(max(0.0, nxt - time.perf_counter()))
            else:
                self._one()
                self._stop.wait(self.period_s)

    def start(self):
        self.t0 = time.perf_counter()
        self._thr = threading.Thread(target=self._loop, daemon=True, name=f"probe-loop-{self.name}")
        self._thr.start()
        return self

    def stop(self, drain_s=300.0):
        self._stop.set()
        if self._thr:
            self._thr.join(timeout=drain_s)
        end = time.time() + drain_s
        for f in self._pending:
            try:
                f.result(timeout=max(0.1, end - time.time()))
            except Exception:
                pass
        self._pool.shutdown(wait=False)
        return self.samples

    def window(self, a_ms, b_ms):
        return [s for s in self.samples if a_ms <= s["t_ms"] < b_ms]


def health_call(base_url):
    c = httpx.Client(base_url=base_url, limits=httpx.Limits(max_keepalive_connections=0))  # new connection per call, like nginx -> backend

    def call(timeout):
        return c.get("/health", timeout=timeout).status_code

    return call


def heartbeat_call(base_url, sid):
    c = httpx.Client(base_url=base_url, limits=httpx.Limits(max_keepalive_connections=0))  # new connection per call, like nginx -> backend

    def call(timeout):  # own rate-limit bucket via X-Session-ID (see module doc)
        return c.post(f"/session/heartbeat/{sid}", headers={"X-Session-ID": sid}, timeout=timeout).status_code

    return call


def script_call(base_url, sid, png, engine="decimer"):
    c = httpx.Client(base_url=base_url, limits=httpx.Limits(max_keepalive_connections=0))  # new connection per call, like nginx -> backend

    def call(timeout):
        r = c.post("/latest/ocsr/generate_smiles", headers={"X-Session-ID": sid},
                   files={"image_file": ("probe.png", png, "image/png")}, data={"engine": engine, "hand_drawn": "false"},
                   timeout=timeout)
        return r.status_code

    return call


def lat_stats(samples):
    ok = [s["ms"] for s in samples if s["status"] == 200]
    return {"n": len(samples), "n_ok": len(ok), "n_error": sum(1 for s in samples if s["error"]),
            "n_429": sum(1 for s in samples if s["status"] == 429), "n_503": sum(1 for s in samples if s["status"] == 503),
            "n_other": sum(1 for s in samples if s["status"] not in (200, 429, 503) and not s["error"]), "ms_ok": stats(ok),
            "all_ms": stats([s["ms"] for s in samples]),
            "share_over_200ms": round(sum(1 for s in samples if s["ms"] > 200) / len(samples), 3) if samples else None}


def logsrc(base_url):
    return client_v1.default_log_source(base_url)


def v1_warmup(base_url, sid, png, eng, timeout=1200) -> dict:
    ts = time.perf_counter()
    try:
        r = httpx.post(f"{base_url}/latest/ocsr/generate_smiles", headers={"X-Session-ID": sid or ""},
                       files={"image_file": ("warm.png", png, "image/png")}, data={"engine": eng}, timeout=timeout)
        return {"ms": round((time.perf_counter() - ts) * 1000, 1), "status": r.status_code}
    except Exception as e:
        return {"error": str(e)[:200]}


class V1Api:
    """The calls the scenarios make, v1 form. load/v2_adapter.py has the same names in v2 form."""
    name = "v1"
    BUILD = client_v1.BUILD
    run_paper = staticmethod(run_paper)
    server_ok = staticmethod(server_ok)
    create_session = staticmethod(create_session)
    remove_session = staticmethod(remove_session)
    health_call = staticmethod(health_call)
    heartbeat_call = staticmethod(heartbeat_call)
    script_call = staticmethod(script_call)
    warmup = staticmethod(v1_warmup)
    logsrc = staticmethod(logsrc)
    abort_all = staticmethod(client_v1.abort_all)

    @staticmethod
    def depict_call(base_url, sid):
        return None  # not measured on v1 (the spec's depict gate is a v2 goal)

    @staticmethod
    def page_errors_of(recs):
        return None  # v1: page errors come from the backend's docker log (logsrc + remote.parse_server_log)


API = V1Api  # set by main() from --client
CLIENT = "v1"


def select_client(name: str):
    return v2_adapter if name == "v2" else V1Api


def big_cap_for(client: str, cap):
    """S2 big-paper OCSR cap: v1 only. v2 runs the big paper in full (the spec gate is 'while it runs')."""
    if client == "v2":
        if cap is not None:
            print(f"--big-cap {cap} ignored for --client v2: the big paper runs full OCSR", flush=True)
        return None
    return cap


def s4_max_segments(client: str):
    return None if client == "v2" else 0  # v2: full pipeline (spec §3 Throughput); v1: segmentation only


def result_path(results_dir: Path, target_name: str, client: str, name: str, tag: str) -> Path:
    prefix = f"{target_name}_v2" if client == "v2" else target_name
    return results_dir / f"{prefix}_{name}_{datetime.now().strftime('%Y%m%dT%H%M%S')}{('_' + tag) if tag else ''}.json"


def guard_enabled(target_name: str, base_url: str) -> bool:
    """The jarvis guard runs for --target jarvis whatever the tunnel port, and for the v1 jarvis port anyway."""
    return target_name == "jarvis" or is_jarvis_url(base_url)


def host_load() -> list | None:
    try:
        return [round(x, 2) for x in os.getloadavg()]
    except OSError:
        return None


LOCAL_TEST_PG = "marcus-v2-postgres-1"


def _walk(x, fn):
    if isinstance(x, dict):
        fn(x)
        for v in x.values():
            _walk(v, fn)
    elif isinstance(x, list):
        for v in x:
            _walk(v, fn)


def scenario_validity(results) -> dict:
    """Every timing verdict, cache-hit count and failed non-page step in a scenario's results (summary level)."""
    verdicts, hits, failed = [], 0, {}

    def fn(d):
        nonlocal hits
        t = d.get("timing")
        if isinstance(t, dict) and "valid" in t:  # each timed run/arm has one verdict carrying its own hit count
            verdicts.append(t["valid"])
            hits += t.get("ocsr_cache_hits") or 0
        for f in d.get("failed_steps") or [] if isinstance(d.get("failed_steps"), list) else []:
            if isinstance(f, dict):
                k = f"{f.get('kind')}:{f.get('status')}:{f.get('error_class')}"
                failed[k] = failed.get(k, 0) + 1

    _walk(results, fn)
    return {"timings": len(verdicts), "all_valid": all(verdicts) if verdicts else None, "ocsr_cache_hits": hits,
            "failed_steps_by_kind": failed}


def breaker_503s(res) -> dict:
    """503 'service unavailable' answers (rate limiter circuit breaker open): adapter calls + paper uploads."""
    papers = []

    def walk(x):
        if isinstance(x, dict):
            fe = x.get("fatal_error")
            if isinstance(fe, str) and fe.startswith("HTTP 503"):
                papers.append(fe)
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(res.get("results"))
    return {"paper_runs_503": len(papers), "paper_runs_503_detail": sorted(set(papers))}


# ------------------------------------------------------------------ scenarios
def s1(base_url, guard, args, res):
    path, meta = fixture(15)
    engines = args.engines
    out = {"fixture": path.name, "expected": 15, "engines": {}}
    res["results"] = out
    png = png_bytes()
    sid = API.create_session(base_url)
    import chem  # goldset standardiser

    exp_keys = {e["inchikey"].split("-")[0] for e in meta["expected"] if e.get("inchikey")}
    for eng in engines:
        if guard.tripped:
            break
        entry = {"runs": []}
        out["engines"][eng] = entry
        # warm-up: first call of an engine loads weights; keep it out of the numbers but record it
        entry["warmup"] = API.warmup(base_url, sid, png, eng, timeout=1200)
        for i in range(args.s1_repeats):
            if guard.tripped:
                break
            cold(f"S1 {eng} run {i}")
            rec = API.run_paper(path, eng, base_url=base_url, paper_id=path.stem, abort=guard.abort, keep_http_log=True,
                                max_segments=args.s1_max_segments, tag="S1", **BIG_TIMEOUTS)
            keys = set()
            for s in rec["segments"]:
                st = chem.standardise(s["smiles"]) if s["smiles"] else None
                if st and st.ok and st.inchikey:
                    keys.add(st.inchikey.split("-")[0])
            run = summarise_run(rec, 15)
            run["fixture_recall_skeleton"] = round(len(keys & exp_keys) / len(exp_keys), 3) if exp_keys else None
            run["lost_pages"] = lost_pages(rec, meta)
            run["segments"] = seg_rows(rec)
            run["http_log"] = rec.get("http_log")
            if CLIENT == "v2":
                run["timing"] = timing_validity(paper_cache_hits(rec), rec.get("failed_steps"), ALLOW_WARM)
            entry["runs"].append(run)
    API.remove_session(base_url, sid)
    res["summary"] = {eng: [{"wall_s": round(r["wall_ms"] / 1000, 1), "segment_s": round((r["segment_ms"] or 0) / 1000, 1),
                              "ocsr_p50_ms": r["ocsr_ms"].get("p50"), "ocsr_p95_ms": r["ocsr_ms"].get("p95"),
                              "segments": r["n_segments"], "recall_skel": r["fixture_recall_skeleton"],
                              "page_errors": len(r["page_errors"]), "lost_pages": r["lost_pages"],
                              "listed": r["segments_listed"], "backend_crash": r["backend_crash"], **v2_extra(r)}
                             for r in e["runs"]] for eng, e in out["engines"].items()}


SEG_KEYS = ("segment_id", "page", "ocsr_ms", "error", "fallback")
SEG_KEYS_V2 = ("ocsr_compute_ms", "ocsr_attempts", "cached", "t_start_ms")


def seg_rows(rec: dict) -> list[dict]:
    keys = SEG_KEYS + (SEG_KEYS_V2 if rec.get("client") == "client_v2" else ())
    return [{k: s.get(k) for k in keys} for s in rec["segments"]]


def v2_extra(r: dict) -> dict:
    """Summary keys only v2 has (absent for v1, so v1 summaries stay as they were)."""
    if "segment_compute_ms" not in r:
        return {}
    ms = r.get("segment_compute_ms")
    return {"segment_compute_s": None if ms is None else round(ms / 1000, 1),
            "ocsr_compute_p50_ms": r["ocsr_compute_ms"].get("p50"), "ocsr_cache_hits": r.get("ocsr_cache_hits"),
            "first_segment_start_s": r.get("first_segment_start_s"), "first_smiles_s": r.get("first_smiles_s"),
            "ocsr_done_s": r.get("ocsr_done_s"), "fatal_error": r.get("fatal_error"),
            "failed_steps": [f"{f['kind']}:{f['status']}:{f.get('error_class')}" for f in r.get("failed_steps") or []],
            "timing_valid": (r.get("timing") or {}).get("valid")}


def _run_s2_core(base_url, guard, args, big_n, extra_probes=None):
    """Big paper first, small paper(s) 5 s later. Returns dict with both runs and probe samples.
    extra_probes: callable -> {name: started Probe}, stopped when both papers are done."""
    big_path, big_meta = fixture(big_n)
    small_path, small_meta = fixture(15)
    eng = args.engine
    box: dict = {}
    t_start = time.perf_counter()
    hp = Probe("health", API.health_call(base_url), 1.0, abort=guard.abort).start()
    extra = extra_probes(guard.abort) if extra_probes else {}
    cap = big_cap_for(CLIENT, args.big_cap)

    def big():
        box["big_t0"] = time.perf_counter() - t_start
        box["big"] = API.run_paper(big_path, eng, base_url=base_url, paper_id=big_path.stem, max_segments=cap,
                                   abort=guard.abort, keep_http_log=False, tag=f"S2-big{big_n}", **BIG_TIMEOUTS)
        box["big_t1"] = time.perf_counter() - t_start

    th = threading.Thread(target=big, daemon=True)
    th.start()
    smalls = []
    for i in range(args.s2_small_count):
        wait = (5.0 if i == 0 else args.small_gap_s)
        end = time.perf_counter() + wait
        while time.perf_counter() < end and not guard.tripped:
            time.sleep(0.1)
        if guard.tripped:
            break
        sm_t0 = time.perf_counter() - t_start
        sm = {"submitted_at_s": round(sm_t0, 2)}

        def run_small(sm=sm):
            sm["rec"] = API.run_paper(small_path, eng, base_url=base_url, paper_id=small_path.stem, abort=guard.abort,
                                      keep_http_log=True, tag=f"S2-small-{big_n}", **BIG_TIMEOUTS)

        t = threading.Thread(target=run_small, daemon=True)
        t.start()
        sm["thread"] = t
        smalls.append(sm)
    for sm in smalls:
        sm["thread"].join()
    th.join()
    probes = {"health": hp.stop(), **{k: p.stop() for k, p in extra.items()}}
    return box, smalls, probes, small_meta, big_meta


def depict_probe(base_url, args, abort=None):
    """{'depict': Probe} for v2 (POST /tools/depict, own owner), {} for v1."""
    sid = API.create_session(base_url) if CLIENT == "v2" else None
    call = API.depict_call(base_url, sid) if sid else None
    return {"depict": Probe("depict", call, args.depict_period_s, timeout_s=60, abort=abort).start()} if call else {}


def s2(base_url, guard, args, res, big_n=None, with_script=False):
    big_n = big_n or args.s2_big_size
    sess: dict = {}

    def extra(abort):
        probes = depict_probe(base_url, args, abort)
        if with_script:
            sess["sid"] = API.create_session(base_url) or "x"
            probes["script"] = Probe("script", API.script_call(base_url, sess["sid"], png_bytes(), args.engine),
                                     args.s5_period_s, mode="closed", timeout_s=900, abort=abort).start()
        return probes

    box, smalls, probes, small_meta, big_meta = _run_s2_core(base_url, guard, args, big_n, extra_probes=extra)
    API.remove_session(base_url, sess.get("sid"))
    big = box.get("big")
    out = {"engine": args.engine, "client": CLIENT, "big_structures": big_n, "big_ocsr_cap": None if CLIENT == "v2" else args.big_cap,
           "small_count": len(smalls), "big": summarise_run(big, big_n) if big else None,
           "big_started_s": box.get("big_t0"), "big_finished_s": box.get("big_t1"),
           "small": [], "health_probe": lat_stats(probes["health"]), "health_samples": probes["health"]}
    if "depict" in probes:
        out["depict_probe"] = lat_stats(probes["depict"])
        out["depict_samples"] = probes["depict"]
    base = args.s1_reference.get(args.engine) if args.s1_reference else None
    for sm in smalls:
        rec = sm.get("rec")
        if not rec:
            continue
        d = summarise_run(rec, 15)
        d["submitted_at_s"] = sm["submitted_at_s"]
        d["extract_segments_ms"] = rec["segment_ms"]
        d["during_big_run"] = (sm["submitted_at_s"] + rec["wall_ms"] / 1000) < (box.get("big_t1") or 1e9)
        d["slowdown_vs_s1"] = round(rec["wall_ms"] / base["wall_ms"], 2) if base else None
        d.update(fairness_fields(rec))
        # v1-comparable (v1 wall ends at the last OCSR answer; a v2 paper also waits for docling/doi)
        d["slowdown_ocsr_done_vs_s1"] = (round(d["ocsr_done_s"] / base["ocsr_done_s"], 2)
                                         if base and base.get("ocsr_done_s") and d.get("ocsr_done_s") else None)
        d["segments"] = seg_rows(rec)
        d["http_log"] = rec.get("http_log")
        out["small"].append(d)
    if with_script:
        out["script_user"] = {"period_s": args.s5_period_s, **lat_stats(probes.get("script") or []),
                              "samples": probes.get("script")}
        if hasattr(sess.get("sid"), "owners_used"):
            out["script_user"]["owners_used"] = sess["sid"].owners_used
            out["script_user"]["image_jobs"] = sess["sid"].jobs
        out["script_user"]["ocsr_cache_hits"] = v2_adapter.image_job_cache_hits(sess.get("sid"))
    out["s1_reference"] = base
    if CLIENT == "v2":
        # the small papers' timings are the gate numbers: their hits and failed steps decide; the big paper's (and
        # the script user's) cache hits count too, since a warm big paper is not "heavy work"
        hits = sum(d.get("ocsr_cache_hits") or 0 for d in out["small"]) + ((out["big"] or {}).get("ocsr_cache_hits") or 0)
        hits += (out.get("script_user") or {}).get("ocsr_cache_hits") or 0
        out["timing"] = timing_validity(hits, [f for d in out["small"] for f in d.get("failed_steps") or []], ALLOW_WARM)
    walls = [d["wall_ms"] / 1000 for d in out["small"]]
    res["results"] = out
    res["summary"] = {"small_wall_s": [round(w, 1) for w in walls], "small_wall_p95_s": pct(walls, 95),
                      "small_slowdown_vs_s1": [d["slowdown_vs_s1"] for d in out["small"]],
                      "small_first_segment_start_s": [d["first_segment_start_s"] for d in out["small"]],
                      "small_first_smiles_s": [d["first_smiles_s"] for d in out["small"]],
                      "small_ocsr_done_s": [d["ocsr_done_s"] for d in out["small"]],
                      "small_slowdown_ocsr_done_vs_s1": [d["slowdown_ocsr_done_vs_s1"] for d in out["small"]],
                      "small_during_big_run": [d["during_big_run"] for d in out["small"]],
                      "big_wall_s": round(big["wall_ms"] / 1000, 1) if big else None,
                      "big_segment_s": round((big["segment_ms"] or 0) / 1000, 1) if big else None,
                      "big_segments": len(big["segments"]) if big else None,
                      "health_ms": out["health_probe"]["ms_ok"], "health_over_200ms": out["health_probe"]["share_over_200ms"],
                      "health_n_503": out["health_probe"]["n_503"]}
    if CLIENT == "v2":
        res["summary"]["timing_valid"] = out["timing"]["valid"]
        res["summary"]["ocsr_cache_hits"] = out["timing"]["ocsr_cache_hits"]
        res["summary"]["big_failed_steps"] = [f"{f['kind']}:{f['status']}:{f.get('error_class')}"
                                              for f in (out["big"] or {}).get("failed_steps") or []]
    if "depict_probe" in out:
        res["summary"]["depict_ms"] = out["depict_probe"]["all_ms"]
        res["summary"]["depict_p95_ms"] = out["depict_probe"]["all_ms"].get("p95")
        res["summary"]["depict_n_ok"] = out["depict_probe"]["n_ok"]


def s3(base_url, guard, args, res):
    path, meta = fixture(args.s3_size)
    sid = API.create_session(base_url)
    hp = Probe("health", API.health_call(base_url), 1.0, abort=guard.abort).start()
    bp = Probe("heartbeat", API.heartbeat_call(base_url, sid or "none"), 1.0, abort=guard.abort).start()
    dp = depict_probe(base_url, args, guard.abort).get("depict")
    probes = [("health", hp), ("heartbeat", bp)] + ([("depict", dp)] if dp else [])
    idle_s = args.s3_idle_s
    guard.abort.wait(idle_s)
    t_a = (time.perf_counter() - hp.t0) * 1000
    # segmentation only, as v1 (S3 tests event-loop blocking by segmentation); engine: v1 decimer, v2 --engine
    eng = "decimer" if CLIENT == "v1" else args.engine
    rec = API.run_paper(path, eng, base_url=base_url, paper_id=path.stem, max_segments=0, abort=guard.abort, tag="S3",
                        **BIG_TIMEOUTS)
    t_b = (time.perf_counter() - hp.t0) * 1000
    guard.abort.wait(idle_s)
    samples_by = {name: pr.stop() for name, pr in probes}
    # all probes share hp's clock origin within a few ms (started one after the other); depict is shifted to it
    if dp:
        off = (dp.t0 - hp.t0) * 1000
        for x in samples_by["depict"]:
            x["t_ms"] = round(x["t_ms"] + off, 1)
    API.remove_session(base_url, sid)
    out = {"fixture": path.name, "engine": eng, "segmentation_window_ms": [round(t_a), round(t_b)],
           "run": summarise_run(rec, meta["n_structures"])}
    for name, samples in samples_by.items():
        out[name] = {"idle_before": lat_stats([s for s in samples if s["t_ms"] < t_a]),
                     "during_segmentation": lat_stats([s for s in samples if t_a <= s["t_ms"] < t_b]),
                     "after": lat_stats([s for s in samples if s["t_ms"] >= t_b]),
                     "all_samples": samples}
    res["results"] = out
    res["summary"] = {n: {"idle_p95_ms": out[n]["idle_before"]["all_ms"].get("p95"),
                          "during_p50_ms": out[n]["during_segmentation"]["all_ms"].get("p50"),
                          "during_p95_ms": out[n]["during_segmentation"]["all_ms"].get("p95"),
                          "during_max_ms": out[n]["during_segmentation"]["all_ms"].get("max"),
                          "during_n": out[n]["during_segmentation"]["n"], "during_n_error": out[n]["during_segmentation"]["n_error"],
                          "during_n_429": out[n]["during_segmentation"]["n_429"],
                          "during_n_503": out[n]["during_segmentation"]["n_503"]} for n in samples_by}
    res["summary"]["segmentation_s"] = round((t_b - t_a) / 1000, 1)
    if dp:
        res["summary"]["depict_p95_ms"] = res["summary"]["depict"]["during_p95_ms"]


def single_page_pdfs(n_pages: int) -> list[tuple[Path, int]]:
    """One-page PDFs cut from synth_190 (8 structures each): no page-level threading inside a request."""
    import pymupdf

    src, meta = fixture(190)
    outdir = make_fixtures.OUT / "pages"
    outdir.mkdir(parents=True, exist_ok=True)
    res = []
    for p in range(n_pages):
        dst = outdir / f"synth190_p{p:02d}.pdf"
        if not dst.exists():
            d = pymupdf.open(src)
            d.select([p])
            d.save(dst)
        res.append((dst, meta["per_page"][p]))
    return res


def s4(base_url, guard, args, res):
    n = args.s4_size
    path, meta = fixture(n)
    src = API.logsrc(base_url)
    arms = []
    res["results"] = {"fixture": path.name, "expected_each": n, "arms": arms,
                      "note": ("page errors come from backend docker logs in the arm's time window (all papers of the arm together)"
                               if CLIENT == "v1" else "page errors come from each paper's failed page steps")}

    eng = "decimer" if CLIENT == "v1" else args.engine
    depth = s4_max_segments(CLIENT)
    res["results"]["engine"] = eng
    res["results"]["ocsr"] = "segmentation only" if depth == 0 else "full pipeline (segmentation + OCSR)"

    def one(tag, p=path):
        return API.run_paper(p, eng, base_url=base_url, paper_id=p.stem, max_segments=depth, abort=guard.abort,
                             log_source=False, tag=tag, **BIG_TIMEOUTS)

    def run_arm(kind, mode, repeat, paths, expected, per_page):
        """paths: PDFs submitted; sequential = one after the other, concurrent = all at the same moment.
        per_page: each paper's fixture structure count per page (for lost pages)."""
        if guard.tripped or not API.server_ok(base_url):
            res["results"]["stopped"] = "guard tripped" if guard.tripped else "backend not answering /health"
            return False
        cold(f"S4 {kind} {mode} repeat {repeat}")
        mark = src.mark() if src else None
        t0 = time.perf_counter()
        if mode == "sequential":
            recs = [one(f"S4-{kind}-{mode}-{repeat}-{k}", p) for k, p in enumerate(paths)]
        else:
            bar = threading.Barrier(len(paths))
            recs = [None] * len(paths)

            def worker(k):
                bar.wait()
                recs[k] = one(f"S4-{kind}-{mode}-{repeat}-{k}", paths[k])

            ths = [threading.Thread(target=worker, args=(k,)) for k in range(len(paths))]
            [t.start() for t in ths]
            [t.join() for t in ths]
        wall = time.perf_counter() - t0
        parsed = remote.parse_server_log(src.since(mark)) if src and mark is not None else None
        pe = parsed["page_errors"] if parsed else API.page_errors_of(recs)
        arms.append({"kind": kind, "mode": mode, "repeat": repeat, "wall_s": round(wall, 1), "expected_each": expected,
                     "papers": [{"file": p.name, "segments_listed": x["segments_listed"], "segments_reported": x["segments_reported"],
                                 "segment_ms": x["segment_ms"], "wall_ms": x["wall_ms"], "fatal_error": x["fatal_error"],
                                 "pages_total": x["pages_total"], "listed_pages": x.get("listed_pages"),
                                 "segments_with_smiles": sum(1 for s in x["segments"] if s.get("smiles")),
                                 "ocsr_errors": sum(1 for s in x["segments"] if s.get("error")),
                                 "segment_compute_ms": x.get("segment_compute_ms"),
                                 "ocsr_done_ms": x.get("ocsr_done_ms"), "ocsr_cache_hits": paper_cache_hits(x),
                                 "failed_steps": x.get("failed_steps") or [], "cancelled": x.get("cancelled"),
                                 "lost_pages": lost_pages(x, per_page[k])}
                                for k, (p, x) in enumerate(zip(paths, recs))],
                     "page_errors": pe, "page_error_count": len(pe) if pe is not None else None,
                     "server_segment_s": parsed["server_segment_s"] if parsed else None,
                     "log_keywords": parsed["keyword_counts"] if parsed else None,
                     "backend_crash": parsed["backend_crash"] if parsed else None,
                     "error_pages_by_batch4": _batches(pe) if pe else {}})
        if CLIENT == "v2":
            arms[-1]["timing"] = timing_validity(sum(paper_cache_hits(x) for x in recs),
                                                 [f for x in recs for f in x.get("failed_steps") or []], ALLOW_WARM)
        return True

    # Part 1: two multi-page papers, sequential vs concurrent (the plan's S4). v2: two DIFFERENT papers (the two
    # halves of the fixture), since a second copy of the same PDF gives the same crops = OCSR cache hits.
    two = s4_two_paper_paths(CLIENT, path, split=lambda: half_pdfs(n))
    pp = meta["per_page"]
    two_pp = [pp, pp] if two[0] == two[1] else [pp[:len(pp) // 2], pp[len(pp) // 2:]]
    res["results"]["two_papers"] = [p.name for p in two]
    for r in range(args.s4_repeats):
        for mode in ("sequential", "concurrent"):
            if not run_arm("two_papers", mode, r, list(two), n, two_pp):
                break
    # Part 2 (control): one-page PDFs, so no thread pool inside a request. If errors appear only in part 1,
    # the page threads of ONE request cause them; if they appear here too, requests overlap on the model.
    if args.s4_single_pages > 0 and not guard.tripped:
        sp = single_page_pdfs(args.s4_single_pages)
        for r in range(args.s4_repeats):
            for mode in ("sequential", "concurrent"):
                if not run_arm("single_pages", mode, r, [p for p, _ in sp], [e for _, e in sp], [[e] for _, e in sp]):
                    break
    res["summary"] = _s4_summary(arms, n, meta)


def half_pdfs(n: int) -> tuple[Path, Path]:
    """The fixture cut into its first and second half of pages (same fixture, no new paper, distinct crops)."""
    import pymupdf

    src, meta = fixture(n)
    outdir = make_fixtures.OUT / "halves"
    outdir.mkdir(parents=True, exist_ok=True)
    half = meta["pages"] // 2
    out = []
    for k, pages in enumerate((list(range(0, half)), list(range(half, meta["pages"])))):
        dst = outdir / f"{src.stem}_half{k}.pdf"
        if not dst.exists():
            d = pymupdf.open(src)
            d.select(pages)
            d.save(dst)
        out.append(dst)
    return out[0], out[1]


def s4_two_paper_paths(client: str, path: Path, split) -> tuple[Path, Path]:
    """v1: the same PDF twice (its S4 question is page threads). v2: two different halves (cold OCSR cache)."""
    return split() if client == "v2" else (path, path)


def _batches(errs):
    out = {}
    for e in errs:
        out.setdefault(e["page"] // 4, []).append(e["page"])
    return {str(k): sorted(v) for k, v in sorted(out.items())}


def _s4_summary(arms, n, meta):
    by = {}
    for a in arms:
        key = f"{a['kind']}/{a['mode']}"
        d = by.setdefault(key, {"arms": 0, "papers": 0, "page_errors": 0, "segments_found": [], "wall_s": [], "layers": {},
                                "crashes": 0, "lost_pages": 0, "all_segment_counts_equal": True})
        d["arms"] += 1
        d["papers"] += len(a["papers"])
        d["page_errors"] += a["page_error_count"] or 0
        d["segments_found"] += [p["segments_listed"] for p in a["papers"]]
        d["wall_s"].append(a["wall_s"])
        d["crashes"] += 1 if a.get("backend_crash") else 0
        d["lost_pages"] += sum(len(p.get("lost_pages") or []) for p in a["papers"])
        for e in a["page_errors"] or []:
            d["layers"][e.get("layer_type") or "?"] = d["layers"].get(e.get("layer_type") or "?", 0) + 1
    for d in by.values():
        d["all_segment_counts_equal"] = len(set(d["segments_found"])) <= 1
    # share of errors whose 4-page batch has at least one more error (intra-request threads)
    multi = tot = 0
    for a in arms:
        for pages in a["error_pages_by_batch4"].values():
            tot += len(pages)
            if len(pages) > 1:
                multi += len(pages)
    by["errors_in_batches_with_2plus_errors"] = {"errors": tot, "in_multi_error_batches": multi}
    by["expected_segments_two_papers_each"] = n
    by["pages_each"] = meta["pages"]
    # spec §3 Throughput (v2: full pipeline): two papers at once finish faster than one after the other
    for kind in ("two_papers", "single_pages"):
        seq, con = by.get(f"{kind}/sequential"), by.get(f"{kind}/concurrent")
        if seq and con and seq["wall_s"] and con["wall_s"]:
            ms, mc = sum(seq["wall_s"]) / len(seq["wall_s"]), sum(con["wall_s"]) / len(con["wall_s"])
            timings = [a.get("timing") for a in arms if a["kind"] == kind and a.get("timing") is not None]
            valid = all(t.get("valid") for t in timings)
            sp = round(ms / mc, 2) if mc else None
            cmp_ = {"sequential_mean_s": round(ms, 1), "concurrent_mean_s": round(mc, 1), "valid": valid}
            if valid:
                cmp_.update(speedup=sp, concurrent_faster=mc < ms)
            else:  # R21 / I2: an arm with cache hits or a failed docling/doi step is no timing
                cmp_.update(speedup=None, concurrent_faster=None, speedup_invalid=sp,
                            invalid_reasons=sorted({r for t in timings for r in t.get("reasons", [])}))
            by[f"{kind}_concurrent_vs_sequential"] = cmp_
    for a in arms:
        key = f"{a['kind']}/{a['mode']}"
        by[key].setdefault("segments_with_smiles", []).extend(p.get("segments_with_smiles") for p in a["papers"])
        by[key]["ocsr_errors"] = by[key].get("ocsr_errors", 0) + sum(p.get("ocsr_errors") or 0 for p in a["papers"])
        by[key]["fatal_errors"] = by[key].get("fatal_errors", 0) + sum(1 for p in a["papers"] if p.get("fatal_error"))
    return by


def s5(base_url, guard, args, res):
    sid = API.create_session(base_url)
    png = png_bytes()
    alone = Probe("script", API.script_call(base_url, sid or "x", png, args.engine), args.s5_period_s, mode="closed",
                  timeout_s=900, abort=guard.abort).start()
    guard.abort.wait(args.s5_seconds)  # a guard trip ends the alone phase at once
    a = alone.stop()
    res["results"] = {"engine": args.engine, "client": CLIENT, "period_s": args.s5_period_s, "alone": {**lat_stats(a), "samples": a}}
    if hasattr(sid, "owners_used"):
        res["results"]["alone"]["owners_used"] = sid.owners_used
        res["results"]["alone"]["image_jobs"] = sid.jobs
    hits = v2_adapter.image_job_cache_hits(sid)
    res["results"]["alone"]["timing"] = timing_validity(hits, [], getattr(args, "allow_warm_cache", False))
    res["summary"] = {"alone_ms_ok": res["results"]["alone"]["ms_ok"], "n_429": res["results"]["alone"]["n_429"],
                      "n_503": res["results"]["alone"]["n_503"], "alone_n_not_ok": res["results"]["alone"]["n"] - res["results"]["alone"]["n_ok"],
                      "alone_ocsr_cache_hits": hits, "alone_timing_valid": res["results"]["alone"]["timing"]["valid"]}
    API.remove_session(base_url, sid)
    if not args.s5_skip_during and not guard.tripped:
        sub = {}
        cold("S5 during-S2 part")
        s2(base_url, guard, args, sub, with_script=True)
        su = sub["results"]["script_user"]
        res["results"]["during_s2"] = {**{k: v for k, v in su.items() if k != "samples"}, "samples": su["samples"],
                                       "s2_small_wall_s": sub["summary"]["small_wall_s"], "s2_health": sub["summary"]["health_ms"],
                                       "s2_full": sub["results"]}
        res["summary"]["during_s2_ms_ok"] = su["ms_ok"]
        res["summary"]["during_s2_n_error"] = su["n_error"]
        res["summary"]["during_s2_all_ms"] = su["all_ms"]
        res["summary"]["during_s2_n_429"] = su["n_429"]
        res["summary"]["during_s2_n_503"] = su["n_503"]
        res["summary"]["during_s2_n_not_ok"] = su["n"] - su["n_ok"]
        if "timing_valid" in sub["summary"]:
            res["summary"]["during_s2_timing_valid"] = sub["summary"]["timing_valid"]
            res["summary"]["during_s2_ocsr_cache_hits"] = sub["summary"]["ocsr_cache_hits"]
        for k in ("depict_p95_ms", "depict_ms", "small_wall_s", "small_first_segment_start_s", "small_first_smiles_s"):
            if k in sub["summary"]:
                res["summary"][f"during_s2_{k}" if k.startswith("depict") else f"s2_{k}"] = sub["summary"][k]


SCENARIOS = {"S1": s1, "S2": s2, "S2_2020": lambda b, g, a, r: s2(b, g, a, r, big_n=2020), "S3": s3, "S4": s4, "S5": s5}


def load_s1_reference(target_name, results_dir, client="v1") -> dict:
    """Latest S1 wall per engine for this target and client, used for the S2 slowdown factor."""
    ref = {}
    prefix = f"{target_name}_v2" if client == "v2" else target_name
    for f in sorted(results_dir.glob(f"{prefix}_S1_*.json")):
        try:
            d = json.loads(f.read_text())
            if d["config"].get("s1_max_segments") or d["config"].get("tag") == "validation" or d.get("stopped_early"):
                continue  # smoke-test or partial S1 results are not a baseline
            for eng, e in d["results"]["engines"].items():
                runs = [r for r in e["runs"] if r.get("wall_ms") and not r.get("fatal_error")]
                if runs:
                    ref[eng] = {"wall_ms": min(r["wall_ms"] for r in runs), "from": f.name}
                    done = [r["ocsr_done_s"] for r in runs if r.get("ocsr_done_s")]
                    if done:
                        ref[eng]["ocsr_done_s"] = min(done)
        except Exception:
            pass
    return ref


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", choices=list(TARGETS), required=True)
    ap.add_argument("--client", choices=["v1", "v2"], default="v1",
                    help="v1 = current build (client_v1); v2 = backend-v2 through nginx (load/v2_adapter.py)")
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--scenarios", nargs="+", default=["S1"], choices=list(SCENARIOS))
    ap.add_argument("--engines", nargs="+", default=ENGINES, choices=ENGINES + V2_ONLY_ENGINES, help="S1 engines")
    ap.add_argument("--engine", default="decimer", choices=ENGINES + V2_ONLY_ENGINES,
                    help="engine for S2-S5 (v2: also S3/S4); 'fake' only with --client v2 on the fake stack")
    ap.add_argument("--s1-repeats", type=int, default=1)
    ap.add_argument("--s1-max-segments", type=int, default=None, help="smoke tests only: OCSR the first N segments")
    ap.add_argument("--big-cap", type=int, default=80, help="S2: OCSR only the first N segments of the big paper")
    ap.add_argument("--s2-small-count", type=int, default=1)
    ap.add_argument("--s2-big-size", type=int, default=190, choices=[15, 190], help="S2/S5 big paper (15 only for smoke tests on CPU)")
    ap.add_argument("--small-gap-s", type=float, default=10.0)
    ap.add_argument("--s3-size", type=int, default=190, choices=[15, 190, 2020])
    ap.add_argument("--s3-idle-s", type=float, default=15.0)
    ap.add_argument("--s4-size", type=int, default=190, choices=[15, 190])
    ap.add_argument("--s4-repeats", type=int, default=2)
    ap.add_argument("--s4-single-pages", type=int, default=8, help="S4 control: this many one-page PDFs (0 = skip)")
    ap.add_argument("--s5-seconds", type=float, default=60.0)
    ap.add_argument("--s5-period-s", type=float, default=3.5)
    ap.add_argument("--s5-skip-during", action="store_true")
    ap.add_argument("--depict-period-s", type=float, default=2.0,
                    help="v2: depict probe period in S2/S3/S5 (60 tool calls per owner per minute)")
    ap.add_argument("--prod-stopped", action="store_true",
                    help="jarvis guard, ONLY in the owner's GPU test window with v1 production stopped on purpose: "
                         "production must stay stopped (instead of healthy); GPU memory and ledger rules unchanged")
    ap.add_argument("--cache-pg-container", default=os.environ.get("MARCUS_TEST_PG_CONTAINER"),
                    help="v2: the TEST stack's Postgres container whose OCSR cache is emptied before each scenario, arm "
                         f"and repeat (env MARCUS_TEST_PG_CONTAINER; local default {LOCAL_TEST_PG}; jarvis: the "
                         "marcus-v2-test project's postgres, required). docker exec, so DOCKER_HOST reaches a remote docker")
    ap.add_argument("--allow-warm-cache", action="store_true",
                    help="v2: do not clear the OCSR cache and accept cache hits as valid timings (warm-behaviour runs only)")
    ap.add_argument("--tag", default="", help="added to the result file name")
    a = ap.parse_args(argv)

    global API, CLIENT, CACHE, ALLOW_WARM
    CLIENT, API = a.client, select_client(a.client)
    ALLOW_WARM, CACHE = a.allow_warm_cache, None
    if a.client == "v1" and (a.engine in V2_ONLY_ENGINES or set(a.engines) & set(V2_ONLY_ENGINES)):
        ap.error("engine 'fake' exists only on the v2 fake stack (--client v2)")
    base_url = (a.base_url or (TARGETS_V2 if a.client == "v2" else TARGETS)[a.target]).rstrip("/")
    target._check(base_url)
    if a.client == "v2" and not a.allow_warm_cache:
        container = a.cache_pg_container or (LOCAL_TEST_PG if a.target == "local" else None)
        if not container:
            ap.error("--client v2 needs --cache-pg-container <the test stack's postgres container> (R21: timings on a "
                     "cold OCSR cache), or --allow-warm-cache")
        CACHE = v2_adapter.CacheClear(container, a.target)  # refuses production / non-test containers
    RESULTS.mkdir(exist_ok=True)
    a.s1_reference = load_s1_reference(a.target, RESULTS, a.client)
    for n in {15, 190, 2020}:
        make_fixtures.ensure(n) if n != 2020 or "S2_2020" in a.scenarios or a.s3_size == 2020 else None
    if not API.server_ok(base_url):
        print(f"backend {base_url} is not answering /health", file=sys.stderr)
        return 2
    rc = 0
    for name in a.scenarios:
        if not API.server_ok(base_url, timeout=20):
            print(f"STOP before {name}: backend {base_url} is not answering /health (v1 can crash during segmentation; "
                  f"on jarvis the judge copy must be restarted by its owner).", file=sys.stderr, flush=True)
            rc = rc or 2
            break
        res = {"scenario": name, "target": a.target, "client": a.client, "base_url": base_url, "build": API.BUILD,
               "started_at": utc(), "config": {k: v for k, v in vars(a).items() if k != "s1_reference"},
               "stopped_early": False, "host_load": {"start": host_load()}}
        t0 = time.time()
        a.s1_reference = load_s1_reference(a.target, RESULTS, a.client)  # picks up an S1 file written earlier in this run
        if a.client == "v2":
            v2_adapter.http_events(clear=True)
            v2_adapter.reset_abandon()
            client_v2.created_papers(clear=True)
            v2_adapter.created_image_jobs(clear=True)
        n_clears = len(CACHE.log) if CACHE else 0
        print(f"[{utc()}] {name} on {a.target} ({a.client}) ...", flush=True)
        try:
            with Guard(base_url, name, enabled=guard_enabled(a.target, base_url),
                       prod_expected="stopped" if a.prod_stopped else "running",
                       on_trip=[v2_adapter.abandon_all] if a.client == "v2" else None) as guard:
                try:
                    cold(f"before {name}")
                    SCENARIOS[name](base_url, guard, a, res)
                except Exception as e:  # keep what we have
                    import traceback

                    res["error"] = f"{type(e).__name__}: {e}"
                    res["traceback"] = traceback.format_exc()
                    rc = 1
                res["guard"] = guard.summary()
                res["stopped_early"] = guard.tripped
        except GuardTripped as e:
            res["guard_refused"] = str(e)
            res["stopped_early"] = True
            rc = 3
        res["finished_at"] = utc()
        res["duration_s"] = round(time.time() - t0, 1)
        res["host_load"]["end"] = host_load()
        if a.client == "v2":
            ev = v2_adapter.http_events(clear=True)
            res["v2_http_errors"] = {"n": len(ev), "by_status": {str(k): sum(1 for e in ev if e["status"] == k)
                                                                 for k in sorted({e["status"] for e in ev})}, "events": ev[:500]}
            res["v2_breaker_503"] = {"adapter_calls": v2_adapter.breaker_503_count(ev), **breaker_503s(res)}
            res["v2_created"] = {"papers": client_v2.created_papers(clear=True),
                                 "image_jobs": v2_adapter.created_image_jobs(clear=True)}
            res["ocsr_cache"] = {"cleared": CACHE.log[n_clears:] if CACHE else [], "allow_warm_cache": a.allow_warm_cache,
                                 "container": CACHE.container if CACHE else None}
            res["validity"] = scenario_validity(res.get("results"))
            if isinstance(res.get("summary"), dict):
                res["summary"]["timing_valid_all"] = res["validity"]["all_valid"]
                res["summary"]["ocsr_cache_hits_total"] = res["validity"]["ocsr_cache_hits"]
                res["summary"]["failed_steps_by_kind"] = res["validity"]["failed_steps_by_kind"]
                res["summary"]["v2_breaker_503"] = res["v2_breaker_503"]["adapter_calls"] + res["v2_breaker_503"]["paper_runs_503"]
                res["summary"]["host_load"] = res["host_load"]
        fn = result_path(RESULTS, a.target, a.client, name, a.tag)
        fn.write_text(json.dumps(res, indent=1))
        print(f"[{utc()}] {name} done in {res['duration_s']} s -> {fn.name}", flush=True)
        print(json.dumps(res.get("summary"), indent=1)[:3000], flush=True)
        if res["stopped_early"]:
            print(f"STOPPED EARLY: {res.get('guard', {}).get('trip_reason') or res.get('guard_refused')}", flush=True)
            if a.target == "jarvis":
                break
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
