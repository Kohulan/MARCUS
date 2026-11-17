"""Run gold-set papers x engines through client_v1 and append run lines to judges/runs/<name>.jsonl.

    cd judges
    uv run python load/run_goldset.py --name v1-local-smoke --papers PMC7689812 PMC6255373     # 2 papers x 3 engines
    uv run python load/run_goldset.py --name v1-jarvis --base-url http://localhost:29000 --split dev
    uv run python goldset/score.py runs/v1-local-smoke.jsonl --out /tmp/score.json --md /tmp/score.md

Resumable: every finished (paper_id, engine) is appended as one line at once; a second call with the
same --name skips the pairs already in the file (use --retry-failed to redo runs that ended with a fatal
error). Papers run one after the other and engines one after the other, exactly like one user.

Selection:  --papers ids | --split dev|test|all (default all) | --order manifest|pages|bytes | --limit N
            (the limit applies after the split and order). --engines (default decimer molnextr molscribe).

--client v2 drives backend-v2 (common/client_v2.py) and writes the same run lines (build "v2-<git hash>").

Each upload gets a unique file name and unique bytes so every run really segments (see client_v1).
--reuse-segmentation instead keeps the upload stable per paper: the first engine segments, the next
engines reuse it (what a user does when switching engine); their segment_ms is then about 0 and
``segments_already_existed`` is true in the line.

On the jarvis copy (port 29000) the whole run is wrapped in guard_jarvis.Guard (production health and free
GPU memory checked every 30 s); if it trips the run stops and can be resumed later.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from common import client_v1, client_v2, target  # noqa: E402
from common.client_v1 import sha256_file  # noqa: E402

ENGINES = ["decimer", "molnextr", "molscribe"]


def load_manifest() -> list[dict]:
    return [json.loads(l) for l in open(ROOT / "goldset" / "manifest.jsonl")]


def done_pairs(path: Path, retry_failed: bool) -> set[tuple[str, str]]:
    done = set()
    if path.exists():
        for line in open(path):
            try:
                r = json.loads(line)
            except Exception:
                continue  # a half-written last line from a crash: ignore, it will be redone
            if r.get("aborted"):
                continue
            if retry_failed and r.get("fatal_error"):
                continue
            done.add((r["paper_id"], r["engine"]))
    return done


def select(manifest: list[dict], args) -> list[dict]:
    rows = manifest
    if args.papers:
        by_id = {r["paper_id"]: r for r in manifest}
        missing = [p for p in args.papers if p not in by_id]
        if missing:
            raise SystemExit(f"unknown paper ids: {missing}")
        rows = [by_id[p] for p in args.papers]
    elif args.split != "all":
        rows = [r for r in rows if r["split"] == args.split]
    if args.order == "pages":
        rows = sorted(rows, key=lambda r: (r["pages"], r["paper_id"]))
    elif args.order == "bytes":
        rows = sorted(rows, key=lambda r: (r["bytes"], r["paper_id"]))
    if args.limit:
        rows = rows[: args.limit]
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", required=True, help="output file runs/<name>.jsonl")
    ap.add_argument("--base-url", default=None, help="default: MARCUS_BACKEND_URL or http://localhost:19000")
    ap.add_argument("--papers", nargs="*", default=None)
    ap.add_argument("--split", choices=["dev", "test", "all"], default="all")
    ap.add_argument("--order", choices=["manifest", "pages", "bytes"], default="manifest")
    ap.add_argument("--limit", type=int, default=0, help="at most this many papers (after split and order)")
    ap.add_argument("--engines", nargs="*", default=ENGINES, choices=ENGINES)
    ap.add_argument("--client", choices=["v1", "v2"], default="v1",
                    help="v1: the current build (default); v2: backend-v2 API (default base URL still needs --base-url)")
    ap.add_argument("--retry-failed", action="store_true")
    ap.add_argument("--reuse-segmentation", action="store_true")
    ap.add_argument("--max-segments", type=int, default=None, help="OCSR only the first N segments (smoke tests)")
    ap.add_argument("--ocsr-timeout-s", type=float, default=client_v1.UI_OCSR_TIMEOUT_S, help="per OCSR call, UI uses 60")
    ap.add_argument("--segment-timeout-s", type=float, default=client_v1.UI_SEGMENT_TIMEOUT_S, help="extract_segments call, UI uses 300")
    ap.add_argument("--stop-after-down", type=int, default=2, help="stop after this many consecutive connection failures")
    ap.add_argument("--no-logs", action="store_true", help="do not read backend docker logs for page errors")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    run_paper = client_v2.run_paper if args.client == "v2" else client_v1.run_paper

    base_url = (args.base_url or target.backend_url()).rstrip("/")
    target._check(base_url)  # refuses production hostnames
    out = ROOT / "runs" / f"{args.name}.jsonl"
    out.parent.mkdir(exist_ok=True)
    manifest = select(load_manifest(), args)
    done = done_pairs(out, args.retry_failed)
    todo = [(r, e) for r in manifest for e in args.engines if (r["paper_id"], e) not in done]
    print(f"{len(manifest)} papers x {len(args.engines)} engines = {len(manifest) * len(args.engines)} runs; "
          f"{len(done)} already in {out.name}; {len(todo)} to do; target {base_url}", flush=True)
    if args.dry_run or not todo:
        return 0

    from guard_jarvis import Guard, GuardTripped, is_jarvis_url

    log_source = False if args.no_logs else "auto"
    t_all = time.time()
    n_done = 0
    consecutive_down = 0
    try:
        with Guard(base_url, f"goldset:{args.name}") as guard:
            for r, engine in todo:
                if guard.tripped:
                    break
                pdf = ROOT / r["pdf_path"]
                sha = sha256_file(pdf)
                if sha != r["sha256"]:
                    print(f"SKIP {r['paper_id']}: sha256 differs from manifest ({sha[:12]} != {r['sha256'][:12]})", flush=True)
                    continue
                rec = run_paper(pdf, engine, base_url=base_url, paper_id=r["paper_id"], reuse_upload=args.reuse_segmentation,
                                max_segments=args.max_segments, abort=guard.abort, log_source=log_source,
                                ocsr_timeout_s=args.ocsr_timeout_s, segment_timeout_s=args.segment_timeout_s,
                                tag=f"goldset:{args.name}")
                if rec.get("aborted"):
                    print(f"ABORTED {r['paper_id']} {engine}: {guard.tripped_reason}", flush=True)
                    break
                with open(out, "a") as f:
                    f.write(json.dumps(rec) + "\n")
                n_done += 1
                down = bool(rec["fatal_error"]) and rec["fatal_error"].split(":")[0] in ("ConnectError", "RemoteProtocolError", "ReadError", "ConnectTimeout")
                consecutive_down = consecutive_down + 1 if down else 0
                if rec.get("ocsr_cache_hits"):
                    print(f"WARNING: {r['paper_id']} {engine}: {rec['ocsr_cache_hits']} OCSR cache hit(s); ocsr_ms and wall_ms "
                          f"are not comparable with v1 (timing needs a cold cache; accuracy is fine)", flush=True)
                n_err = sum(1 for s in rec["segments"] if s["error"])
                print(f"[{n_done}/{len(todo)}] {r['paper_id']} {engine:9s} wall {rec['wall_ms'] / 1000:7.1f}s  seg {(rec['segment_ms'] or 0) / 1000:6.1f}s  "
                      f"segments {len(rec['segments']):3d}/{rec['segments_reported']}  seg_errors {n_err}  page_errors {len(rec['page_errors'])}  "
                      f"429s {len(rec['rate_limit_events'])}  {'BACKEND CRASH IN LOG ' if rec.get('backend_crash') else ''}{rec['fatal_error'] or ''}", flush=True)
                if consecutive_down >= args.stop_after_down:
                    print(f"STOP: {consecutive_down} runs in a row failed with connection errors; the backend looks down "
                          f"(v1 can crash on multi-page PDFs). Restart it and rerun with the same --name to resume "
                          f"(add --retry-failed to redo the failed runs).", flush=True)
                    break
    except GuardTripped as e:
        print(f"guard refused to start or tripped: {e}", flush=True)
        return 2
    print(f"finished {n_done} runs in {(time.time() - t_all) / 60:.1f} min -> {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
