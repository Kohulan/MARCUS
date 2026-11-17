"""Fixture accuracy per engine (spec §3 "Not less accurate"): the S1/S2 fixtures through v1 or v2, scored against the
fixture sidecar (known truth: one structure per slot, page and InChIKey known).

    cd judges
    uv run python load/fixture_accuracy.py --client v1 --target jarvis --base-url http://127.0.0.1:19000 --prod-stopped
    uv run python load/fixture_accuracy.py --client v2 --target jarvis --base-url http://127.0.0.1:18090 --prod-stopped \
        --cache-pg-container marcus-v2-test-postgres-1

Per (fixture, engine), one full run (segmentation + OCSR of every segment) with the shared client (client_v1 /
client_v2.run_paper). A slot counts as an exact match when the standardised full InChIKey of a prediction ON THE SAME
PAGE equals the slot's InChIKey (goldset/chem.py standardisation on both sides); skeleton = InChIKey first block.
Each fixture slot holds a different molecule (190 distinct keys), so page-local matching cannot double count.
v2: the OCSR cache is emptied before every run (R21: the cache key ignores the device, so a GPU rerun of an engine
would otherwise get the CPU answers). Results: load/results/<target>[_v2]_ACC_<time>[_tag].json, rewritten after
every run so a crash of the backend keeps what was measured.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "goldset"))

import chem  # noqa: E402
import make_fixtures  # noqa: E402
import v2_adapter  # noqa: E402
from common import client_v1, client_v2, target  # noqa: E402
from guard_jarvis import Guard, GuardTripped  # noqa: E402

RESULTS = HERE / "results"
ENGINES = ["decimer", "decimer-hand", "molnextr", "molscribe"]
TIMEOUTS = dict(segment_timeout_s=3600, ocsr_timeout_s=900)


def utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def score(rec: dict, meta: dict) -> dict:
    """Exact (full InChIKey) and skeleton (first block) matches per slot, page-local."""
    pred_full: dict[int, set] = {}
    pred_first: dict[int, set] = {}
    seg_rows, n_valid = [], 0
    for s in rec["segments"]:
        st = chem.standardise(s["smiles"]) if s.get("smiles") else None
        ok = bool(st and st.ok and st.inchikey)
        n_valid += ok
        if ok:
            pred_full.setdefault(s["page"], set()).add(st.inchikey)
            pred_first.setdefault(s["page"], set()).add(st.inchikey.split("-")[0])
        seg_rows.append({"segment_id": s.get("segment_id"), "page": s.get("page"), "smiles": s.get("smiles"),
                         "inchikey": st.inchikey if ok else None, "error": s.get("error"),
                         "ocsr_ms": s.get("ocsr_ms"), "ocsr_compute_ms": s.get("ocsr_compute_ms"),
                         "cached": s.get("cached")})
    exact = [e["index"] for e in meta["expected"] if e["inchikey"] in pred_full.get(e["page"], set())]
    skel = [e["index"] for e in meta["expected"] if e["inchikey"].split("-")[0] in pred_first.get(e["page"], set())]
    per_page = meta["per_page"]
    have_pages = {s["page"] for s in rec["segments"] if s.get("page") is not None} | set(rec.get("listed_pages") or [])
    lost = sorted({i for i, n in enumerate(per_page) if n > 0} - have_pages)
    n = len(meta["expected"])
    return {"expected": n, "segments": len(rec["segments"]), "valid_smiles": n_valid,
            "exact": len(exact), "exact_rate": round(len(exact) / n, 4), "skeleton": len(skel),
            "skeleton_rate": round(len(skel) / n, 4), "lost_pages": lost, "exact_slots": exact,
            "seg_rows": seg_rows}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--client", choices=["v1", "v2"], required=True)
    ap.add_argument("--target", choices=["local", "jarvis"], required=True, help="jarvis: guard on (prod-stopped)")
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--sizes", type=int, nargs="+", default=[15, 190], choices=[15, 190])
    ap.add_argument("--engines", nargs="+", default=ENGINES, choices=ENGINES)
    ap.add_argument("--prod-stopped", action="store_true", help="guard: production must stay stopped (GPU window)")
    ap.add_argument("--cache-pg-container", default=None, help="v2: test stack Postgres whose OCSR cache is emptied")
    ap.add_argument("--tag", default="")
    a = ap.parse_args(argv)
    base_url = target._check(a.base_url.rstrip("/"))
    api = client_v2 if a.client == "v2" else client_v1
    cache = None
    if a.client == "v2":
        if not a.cache_pg_container:
            ap.error("--client v2 needs --cache-pg-container (cold cache; the cache key ignores the device)")
        cache = v2_adapter.CacheClear(a.cache_pg_container, a.target)
    RESULTS.mkdir(exist_ok=True)
    prefix = f"{a.target}_v2" if a.client == "v2" else a.target
    out = RESULTS / f"{prefix}_ACC_{datetime.now().strftime('%Y%m%dT%H%M%S')}{('_' + a.tag) if a.tag else ''}.json"
    res = {"kind": "fixture_accuracy", "client": a.client, "target": a.target, "base_url": base_url,
           "build": api.BUILD if a.client == "v1" else f"v2-{client_v2.git_short_hash()}",
           "started_at": utc(), "config": vars(a), "standardisation": chem.STANDARDISATION, "runs": []}
    rc = 0
    try:
        with Guard(base_url, "ACC", enabled=a.target == "jarvis",
                   prod_expected="stopped" if a.prod_stopped else "running") as guard:
            for n in a.sizes:
                path, meta = make_fixtures.ensure(n), make_fixtures.load_meta(n)
                for eng in a.engines:
                    if guard.tripped:
                        break
                    cleared = cache.clear(f"ACC {n} {eng}") if cache else None
                    print(f"[{utc()}] synth_{n:03d} {eng} ...", flush=True)
                    t0 = time.time()
                    try:
                        rec = api.run_paper(path, eng, base_url=base_url, paper_id=path.stem, abort=guard.abort,
                                            tag=f"ACC:{a.tag}", **TIMEOUTS)
                    except Exception as e:  # one engine's failure must not end the other engines' runs (M6)
                        rec = {"segments": [], "wall_ms": 0, "fatal_error": f"{type(e).__name__}: {e}"[:300],
                               "listed_pages": []}
                    sc = score(rec, meta)
                    row = {"fixture": path.stem, "engine": eng, "wall_s": round(rec["wall_ms"] / 1000, 1),
                           "duration_s": round(time.time() - t0, 1), "fatal_error": rec.get("fatal_error"),
                           "aborted": rec.get("aborted"), "backend_crash": rec.get("backend_crash"),
                           "page_errors": rec.get("page_errors"), "failed_steps": rec.get("failed_steps"),
                           "ocsr_cache_hits": rec.get("ocsr_cache_hits"), "cache_cleared_rows": cleared,
                           "segments_listed": rec.get("segments_listed"), "v2_paper_id": rec.get("v2_paper_id"),
                           "engine_versions": sorted({s.get("engine_version") for s in rec["segments"]
                                                      if s.get("engine_version")}),
                           "n_seg_errors": sum(1 for s in rec["segments"] if s.get("error")), **sc}
                    # R21 (M5): a v2 run with an OCSR cache hit is not a cold run; accuracy holds, timings do not
                    row["timing_valid"] = not (a.client == "v2" and (rec.get("ocsr_cache_hits") or 0) > 0)
                    res["runs"].append(row)
                    out.write_text(json.dumps(res, indent=1))
                    print(f"    exact {sc['exact']}/{sc['expected']}  skeleton {sc['skeleton']}  segments "
                          f"{sc['segments']}  lost pages {sc['lost_pages']}  seg errors {row['n_seg_errors']}  "
                          f"wall {row['wall_s']} s  {rec.get('fatal_error') or ''}", flush=True)
            res["guard"] = guard.summary()
    except GuardTripped as e:
        res["guard_refused"] = str(e)
        rc = 3
    res["finished_at"] = utc()
    res["summary"] = {f"{r['fixture']}/{r['engine']}": {"exact": r["exact"], "expected": r["expected"],
                                                         "skeleton": r["skeleton"], "segments": r["segments"],
                                                         "lost_pages": r["lost_pages"], "fatal": r["fatal_error"]}
                      for r in res["runs"]}
    out.write_text(json.dumps(res, indent=1))
    print(json.dumps(res["summary"], indent=1), flush=True)
    print(f"-> {out}", flush=True)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
