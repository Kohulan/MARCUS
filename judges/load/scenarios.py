"""Load and fairness scenarios S1-S5 for the current build (v1). Raw timings go to load/results/*.json.

    cd judges
    uv run python load/scenarios.py --target local  --scenarios S1 S4
    uv run python load/scenarios.py --target jarvis --scenarios S1 S2 S3 S4 S5      # GPU copy, guarded

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
"""
from __future__ import annotations

import argparse
import io
import json
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
from common import client_v1, remote, target  # noqa: E402
from common.client_v1 import run_paper  # noqa: E402
from guard_jarvis import Guard, GuardTripped  # noqa: E402

RESULTS = HERE / "results"
TARGETS = {"local": "http://localhost:19100", "jarvis": "http://localhost:29000"}
ENGINES = ["decimer", "molnextr", "molscribe"]
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
    return out


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

    def __init__(self, name, make_call, period_s=1.0, mode="open", timeout_s=300.0):
        self.name, self.make_call, self.period_s, self.mode, self.timeout_s = name, make_call, period_s, mode, timeout_s
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
        while not self._stop.is_set():
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
            "n_429": sum(1 for s in samples if s["status"] == 429), "ms_ok": stats(ok),
            "all_ms": stats([s["ms"] for s in samples]),
            "share_over_200ms": round(sum(1 for s in samples if s["ms"] > 200) / len(samples), 3) if samples else None}


def logsrc(base_url):
    return client_v1.default_log_source(base_url)


# ------------------------------------------------------------------ scenarios
def s1(base_url, guard, args, res):
    path, meta = fixture(15)
    engines = args.engines
    out = {"fixture": path.name, "expected": 15, "engines": {}}
    res["results"] = out
    png = png_bytes()
    sid = create_session(base_url)
    import chem  # goldset standardiser

    exp_keys = {e["inchikey"].split("-")[0] for e in meta["expected"] if e.get("inchikey")}
    for eng in engines:
        if guard.tripped:
            break
        entry = {"runs": []}
        out["engines"][eng] = entry
        # warm-up: first call of an engine loads weights; keep it out of the numbers but record it
        ts = time.perf_counter()
        try:
            r = httpx.post(f"{base_url}/latest/ocsr/generate_smiles", headers={"X-Session-ID": sid or ""},
                           files={"image_file": ("warm.png", png, "image/png")}, data={"engine": eng}, timeout=1200)
            entry["warmup"] = {"ms": round((time.perf_counter() - ts) * 1000, 1), "status": r.status_code}
        except Exception as e:
            entry["warmup"] = {"error": str(e)[:200]}
        for i in range(args.s1_repeats):
            if guard.tripped:
                break
            rec = run_paper(path, eng, base_url=base_url, paper_id=path.stem, abort=guard.abort, keep_http_log=True,
                            max_segments=args.s1_max_segments, tag="S1", **BIG_TIMEOUTS)
            keys = set()
            for s in rec["segments"]:
                st = chem.standardise(s["smiles"]) if s["smiles"] else None
                if st and st.ok and st.inchikey:
                    keys.add(st.inchikey.split("-")[0])
            run = summarise_run(rec, 15)
            run["fixture_recall_skeleton"] = round(len(keys & exp_keys) / len(exp_keys), 3) if exp_keys else None
            run["lost_pages"] = lost_pages(rec, meta)
            run["segments"] = [{k: s[k] for k in ("segment_id", "page", "ocsr_ms", "error", "fallback")} for s in rec["segments"]]
            run["http_log"] = rec.get("http_log")
            entry["runs"].append(run)
    remove_session(base_url, sid)
    res["summary"] = {eng: [{"wall_s": round(r["wall_ms"] / 1000, 1), "segment_s": round((r["segment_ms"] or 0) / 1000, 1),
                              "ocsr_p50_ms": r["ocsr_ms"].get("p50"), "ocsr_p95_ms": r["ocsr_ms"].get("p95"),
                              "segments": r["n_segments"], "recall_skel": r["fixture_recall_skeleton"],
                              "page_errors": len(r["page_errors"]), "lost_pages": r["lost_pages"],
                              "listed": r["segments_listed"], "backend_crash": r["backend_crash"]} for r in e["runs"]] for eng, e in out["engines"].items()}


def _run_s2_core(base_url, guard, args, big_n, probe_extra=None):
    """Big paper first, small paper(s) 5 s later. Returns dict with both runs and probe samples."""
    big_path, big_meta = fixture(big_n)
    small_path, small_meta = fixture(15)
    eng = args.engine
    box: dict = {}
    t_start = time.perf_counter()
    hp = Probe("health", health_call(base_url), 1.0).start()
    extra = probe_extra() if probe_extra else None

    def big():
        box["big_t0"] = time.perf_counter() - t_start
        box["big"] = run_paper(big_path, eng, base_url=base_url, paper_id=big_path.stem, max_segments=args.big_cap,
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
            sm["rec"] = run_paper(small_path, eng, base_url=base_url, paper_id=small_path.stem, abort=guard.abort,
                                  keep_http_log=True, tag=f"S2-small-{big_n}", **BIG_TIMEOUTS)

        t = threading.Thread(target=run_small, daemon=True)
        t.start()
        sm["thread"] = t
        smalls.append(sm)
    for sm in smalls:
        sm["thread"].join()
    th.join()
    probes = {"health": hp.stop(), "extra": extra.stop() if extra else None}
    return box, smalls, probes, small_meta, big_meta


def s2(base_url, guard, args, res, big_n=None, with_script=False):
    big_n = big_n or args.s2_big_size
    sess: dict = {}
    box, smalls, probes, small_meta, big_meta = _run_s2_core(
        base_url, guard, args, big_n,
        probe_extra=(lambda: Probe("script", script_call(base_url, sess.setdefault("sid", create_session(base_url) or "x"),
                                                         png_bytes(), args.engine),
                                   args.s5_period_s, mode="closed", timeout_s=900).start()) if with_script else None)
    remove_session(base_url, sess.get("sid"))
    big = box.get("big")
    out = {"engine": args.engine, "big_structures": big_n, "big_ocsr_cap": args.big_cap, "small_count": len(smalls),
           "big": summarise_run(big, big_n) if big else None,
           "big_started_s": box.get("big_t0"), "big_finished_s": box.get("big_t1"),
           "small": [], "health_probe": lat_stats(probes["health"]), "health_samples": probes["health"]}
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
        d["segments"] = [{k: s[k] for k in ("segment_id", "page", "ocsr_ms", "error", "fallback")} for s in rec["segments"]]
        d["http_log"] = rec.get("http_log")
        out["small"].append(d)
    if with_script:
        out["script_user"] = {"period_s": args.s5_period_s, **lat_stats(probes["extra"] or []), "samples": probes["extra"]}
    out["s1_reference"] = base
    walls = [d["wall_ms"] / 1000 for d in out["small"]]
    res["results"] = out
    res["summary"] = {"small_wall_s": [round(w, 1) for w in walls], "small_wall_p95_s": pct(walls, 95),
                      "small_slowdown_vs_s1": [d["slowdown_vs_s1"] for d in out["small"]],
                      "big_wall_s": round(big["wall_ms"] / 1000, 1) if big else None,
                      "big_segment_s": round((big["segment_ms"] or 0) / 1000, 1) if big else None,
                      "health_ms": out["health_probe"]["ms_ok"], "health_over_200ms": out["health_probe"]["share_over_200ms"]}


def s3(base_url, guard, args, res):
    path, meta = fixture(args.s3_size)
    sid = create_session(base_url)
    hp = Probe("health", health_call(base_url), 1.0).start()
    bp = Probe("heartbeat", heartbeat_call(base_url, sid or "none"), 1.0).start()
    idle_s = args.s3_idle_s
    time.sleep(idle_s)
    t_a = (time.perf_counter() - hp.t0) * 1000
    rec = run_paper(path, "decimer", base_url=base_url, paper_id=path.stem, max_segments=0, abort=guard.abort, tag="S3",
                    **BIG_TIMEOUTS)
    t_b = (time.perf_counter() - hp.t0) * 1000
    time.sleep(idle_s)
    hs, bs = hp.stop(), bp.stop()
    remove_session(base_url, sid)
    out = {"fixture": path.name, "segmentation_window_ms": [round(t_a), round(t_b)], "run": summarise_run(rec, meta["n_structures"])}
    for name, samples in (("health", hs), ("heartbeat", bs)):
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
                          "during_n_429": out[n]["during_segmentation"]["n_429"]} for n in ("health", "heartbeat")}
    res["summary"]["segmentation_s"] = round((t_b - t_a) / 1000, 1)


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
    src = logsrc(base_url)
    arms = []
    res["results"] = {"fixture": path.name, "expected_each": n, "arms": arms,
                      "note": "page errors come from backend docker logs in the arm's time window (all papers of the arm together)"}

    def one(tag, p=path):
        return run_paper(p, "decimer", base_url=base_url, paper_id=p.stem, max_segments=0, abort=guard.abort,
                         log_source=False, tag=tag, **BIG_TIMEOUTS)

    def run_arm(kind, mode, repeat, paths, expected):
        """paths: PDFs submitted; sequential = one after the other, concurrent = all at the same moment."""
        if guard.tripped or not server_ok(base_url):
            res["results"]["stopped"] = "guard tripped" if guard.tripped else "backend not answering /health"
            return False
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
        pe = parsed["page_errors"] if parsed else None
        arms.append({"kind": kind, "mode": mode, "repeat": repeat, "wall_s": round(wall, 1), "expected_each": expected,
                     "papers": [{"file": p.name, "segments_listed": x["segments_listed"], "segments_reported": x["segments_reported"],
                                 "segment_ms": x["segment_ms"], "wall_ms": x["wall_ms"], "fatal_error": x["fatal_error"],
                                 "pages_total": x["pages_total"], "listed_pages": x.get("listed_pages"),
                                 "lost_pages": lost_pages(x, meta if kind == "two_papers" else [expected[k]])}
                                for k, (p, x) in enumerate(zip(paths, recs))],
                     "page_errors": pe, "page_error_count": len(pe) if pe is not None else None,
                     "server_segment_s": parsed["server_segment_s"] if parsed else None,
                     "log_keywords": parsed["keyword_counts"] if parsed else None,
                     "backend_crash": parsed["backend_crash"] if parsed else None,
                     "error_pages_by_batch4": _batches(pe) if pe else {}})
        return True

    # Part 1: two multi-page papers, sequential vs concurrent (the plan's S4)
    for r in range(args.s4_repeats):
        for mode in ("sequential", "concurrent"):
            if not run_arm("two_papers", mode, r, [path, path], n):
                break
    # Part 2 (control): one-page PDFs, so no thread pool inside a request. If errors appear only in part 1,
    # the page threads of ONE request cause them; if they appear here too, requests overlap on the model.
    if args.s4_single_pages > 0 and not guard.tripped:
        sp = single_page_pdfs(args.s4_single_pages)
        for r in range(args.s4_repeats):
            for mode in ("sequential", "concurrent"):
                if not run_arm("single_pages", mode, r, [p for p, _ in sp], [e for _, e in sp]):
                    break
    res["summary"] = _s4_summary(arms, n, meta)


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
    return by


def s5(base_url, guard, args, res):
    sid = create_session(base_url)
    png = png_bytes()
    alone = Probe("script", script_call(base_url, sid or "x", png, args.engine), args.s5_period_s, mode="closed", timeout_s=900).start()
    time.sleep(args.s5_seconds)
    a = alone.stop()
    res["results"] = {"engine": args.engine, "period_s": args.s5_period_s, "alone": {**lat_stats(a), "samples": a}}
    res["summary"] = {"alone_ms_ok": res["results"]["alone"]["ms_ok"], "n_429": res["results"]["alone"]["n_429"]}
    remove_session(base_url, sid)
    if not args.s5_skip_during and not guard.tripped:
        sub = {}
        s2(base_url, guard, args, sub, with_script=True)
        su = sub["results"]["script_user"]
        res["results"]["during_s2"] = {**{k: v for k, v in su.items() if k != "samples"}, "samples": su["samples"],
                                       "s2_small_wall_s": sub["summary"]["small_wall_s"], "s2_health": sub["summary"]["health_ms"],
                                       "s2_full": sub["results"]}
        res["summary"]["during_s2_ms_ok"] = su["ms_ok"]
        res["summary"]["during_s2_n_error"] = su["n_error"]
        res["summary"]["during_s2_all_ms"] = su["all_ms"]


SCENARIOS = {"S1": s1, "S2": s2, "S2_2020": lambda b, g, a, r: s2(b, g, a, r, big_n=2020), "S3": s3, "S4": s4, "S5": s5}


def load_s1_reference(target_name, results_dir) -> dict:
    """Latest S1 wall per engine for this target, used for the S2 slowdown factor."""
    ref = {}
    for f in sorted(results_dir.glob(f"{target_name}_S1_*.json")):
        try:
            d = json.loads(f.read_text())
            if d["config"].get("s1_max_segments") or d["config"].get("tag") == "validation" or d.get("stopped_early"):
                continue  # smoke-test or partial S1 results are not a baseline
            for eng, e in d["results"]["engines"].items():
                runs = [r for r in e["runs"] if r.get("wall_ms") and not r.get("fatal_error")]
                if runs:
                    ref[eng] = {"wall_ms": min(r["wall_ms"] for r in runs), "from": f.name}
        except Exception:
            pass
    return ref


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", choices=list(TARGETS), required=True)
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--scenarios", nargs="+", default=["S1"], choices=list(SCENARIOS))
    ap.add_argument("--engines", nargs="+", default=ENGINES, choices=ENGINES, help="S1 engines")
    ap.add_argument("--engine", default="decimer", choices=ENGINES, help="engine for S2-S5")
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
    ap.add_argument("--tag", default="", help="added to the result file name")
    a = ap.parse_args(argv)

    base_url = (a.base_url or TARGETS[a.target]).rstrip("/")
    target._check(base_url)
    RESULTS.mkdir(exist_ok=True)
    a.s1_reference = load_s1_reference(a.target, RESULTS)
    for n in {15, 190, 2020}:
        make_fixtures.ensure(n) if n != 2020 or "S2_2020" in a.scenarios or a.s3_size == 2020 else None
    if not server_ok(base_url):
        print(f"backend {base_url} is not answering /health", file=sys.stderr)
        return 2
    rc = 0
    for name in a.scenarios:
        if not server_ok(base_url, timeout=20):
            print(f"STOP before {name}: backend {base_url} is not answering /health (v1 can crash during segmentation; "
                  f"on jarvis the judge copy must be restarted by its owner).", file=sys.stderr, flush=True)
            rc = rc or 2
            break
        res = {"scenario": name, "target": a.target, "base_url": base_url, "build": client_v1.BUILD, "started_at": utc(),
               "config": {k: v for k, v in vars(a).items() if k != "s1_reference"}, "stopped_early": False}
        t0 = time.time()
        a.s1_reference = load_s1_reference(a.target, RESULTS)  # picks up an S1 file written earlier in this run
        print(f"[{utc()}] {name} on {a.target} ...", flush=True)
        try:
            with Guard(base_url, name) as guard:
                try:
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
        fn = RESULTS / f"{a.target}_{name}_{datetime.now().strftime('%Y%m%dT%H%M%S')}{('_' + a.tag) if a.tag else ''}.json"
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
