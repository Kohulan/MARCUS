"""Robustness on v2 (spec §3 "Robust"): a bad PDF fails only its own paper, no worker crash takes the API down,
0 lost pages on the S1 fixture.

    cd judges
    uv run python load/robustness_v2.py --target jarvis --prod-stopped --base-url http://127.0.0.1:18090 \
        --project marcus-v2-test

One good paper (synth_015, 15 structures, engine decimer) starts first; 3 s later every adversarial PDF is uploaded
at once, each by its own owner: the security judge's two payloads (security/payloads.py: garbage %PDF header, XSS
text), the backend's adversarial fixtures (encrypted, zero pages, a PNG named .pdf) and three made here (synth_015
cut in half, a 200x200-inch page whose 300 dpi render would be 60000x60000 px, a page with a 1 GB flate bomb).
While they run, GET /api/v2/health is probed every 0.5 s. Recorded: every paper's final status and failed steps,
the good paper's segments and exact matches against the fixture sidecar, the health probes, and the docker
RestartCount / state of every container of the project before and after (read-only docker inspect).
On jarvis (--target jarvis) the run sits inside the jarvis guard (as fixture_accuracy.py / scenarios.py): GPU
memory, production state, GPU-time ledger; a trip deletes the live papers. Exit code 1 when any verdict is false.
Result: load/results/<target>_v2_ROBUST_<time>.json.
"""
from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
import threading
import time
import zlib
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
for p in (ROOT, HERE, ROOT / "goldset", ROOT / "security"):
    sys.path.insert(0, str(p))

import httpx  # noqa: E402

import fixture_accuracy  # noqa: E402
import make_fixtures  # noqa: E402
import payloads  # noqa: E402
from common import client_v2, target  # noqa: E402
from common.client_v1 import now_iso  # noqa: E402
from guard_jarvis import Guard, GuardTripped  # noqa: E402
from v2.helpers import V2Owner, post_paper, wait_paper  # noqa: E402

RESULTS = HERE / "results"
BACKEND_PDFS = ROOT.parent / "backend-v2" / "tests" / "fixtures" / "pdfs"


def huge_page_pdf() -> bytes:
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=14400, height=14400)  # 200 x 200 inch; 300 dpi -> 60000 x 60000 px
    page.insert_text((72, 100), "huge page")
    return doc.tobytes()


def flate_bomb_pdf() -> bytes:
    """One page whose content stream inflates to 1 GiB of spaces (about 1 MB compressed)."""
    c = zlib.compressobj(9)
    chunk = b" " * (1 << 20)
    body = b"".join(c.compress(chunk) for _ in range(1024)) + c.flush()
    objs = [b"<</Type/Catalog/Pages 2 0 R>>", b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
            b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R>>",
            b"<</Length %d/Filter/FlateDecode>>stream\n" % len(body) + body + b"\nendstream"]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offs = []
    for i, o in enumerate(objs, 1):
        offs.append(out.tell())
        out.write(b"%d 0 obj" % i + o + b"endobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1))
    for o in offs:
        out.write(b"%010d 00000 n \n" % o)
    out.write(b"trailer<</Size %d/Root 1 0 R>>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref))
    return out.getvalue()


def adversarial() -> dict[str, bytes]:
    good = make_fixtures.ensure(15).read_bytes()
    return {
        "judge_garbage": payloads.garbage_pdf_bytes(),
        "judge_xss_text": payloads.xss_pdf_bytes(),
        "encrypted": (BACKEND_PDFS / "encrypted.pdf").read_bytes(),
        "zero_page": (BACKEND_PDFS / "zero_page.pdf").read_bytes(),
        "png_as_pdf": (BACKEND_PDFS / "png_as.pdf").read_bytes(),
        "truncated_synth015": good[: len(good) // 2],
        "huge_page": huge_page_pdf(),
        "flate_bomb_1gib": flate_bomb_pdf(),
    }


def containers(project: str) -> dict:
    """RestartCount / state of every container of the project (read-only). A container that disappears between
    `docker ps` and `docker inspect` is recorded as gone instead of failing the run (M4)."""
    ids = subprocess.run(["docker", "ps", "-a", "-q", "--filter", f"label=com.docker.compose.project={project}"],
                         capture_output=True, text=True, timeout=30).stdout.split()
    out = {}
    for cid in ids:
        f = "{{.Name}}|{{.RestartCount}}|{{.State.Status}}|{{.State.StartedAt}}|{{.State.OOMKilled}}"
        line = subprocess.run(["docker", "inspect", "-f", f, cid], capture_output=True, text=True,
                              timeout=30).stdout.strip()
        parts = line.split("|")
        if len(parts) != 5:
            out[f"gone:{cid}"] = {"restart_count": None, "status": "gone", "started_at": None, "oom_killed": None}
            continue
        name, rc, st, started, oom = parts
        out[name.lstrip("/")] = {"restart_count": int(rc), "status": st, "started_at": started, "oom_killed": oom}
    return out


def restarts(before: dict, after: dict) -> dict:
    """Containers that restarted (count difference), started anew, vanished during the run (gone) or
    disappeared from the project; an empty dict means nothing restarted."""
    out = {n: (after[n]["restart_count"] or 0) - (before.get(n, {}).get("restart_count") or 0)
           for n in after if after[n]["status"] == "gone"
           or after[n]["restart_count"] != before.get(n, {}).get("restart_count")
           or after[n]["started_at"] != before.get(n, {}).get("started_at")}
    out.update({n: "missing after the run" for n in before if n not in after and not n.startswith("gone:")})
    return out


def verdict(good_rec: dict, sc: dict, bad: dict, bad_codes: list, restarted: dict) -> dict:
    """Spec §3 Robust. A bad paper passes when the API refused it with a 4xx (a 5xx is an API failure, M2), or when
    it reached a terminal state on its own (failed, or done for harmless input)."""
    return {
        "good_paper_done_all_15": bool(sc) and sc.get("segments") == 15 and not sc.get("lost_pages")
        and good_rec.get("fatal_error") is None and not good_rec.get("aborted"),
        "every_bad_paper_failed_or_rejected_alone": all(
            400 <= (b.get("upload_status") or 0) < 500 or b.get("status") in ("failed", "done") for b in bad.values()),
        "api_health_always_200": not bad_codes,
        "no_container_restart": not restarted,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--project", required=True, help="compose project of the test stack (docker inspect, read-only)")
    ap.add_argument("--engine", default="decimer")
    ap.add_argument("--target", choices=["local", "jarvis"], required=True,
                    help="jarvis: the run is wrapped in the jarvis guard (GPU memory, production state, GPU-time "
                         "ledger), as fixture_accuracy.py and scenarios.py; also names the result file")
    ap.add_argument("--prod-stopped", action="store_true",
                    help="jarvis guard, ONLY in the owner's GPU window: production v1 must stay stopped")
    a = ap.parse_args(argv)
    base = target._check(a.base_url.rstrip("/"))  # refuses production hosts and ports 8080/9000 on loopback
    res = {"kind": "robustness_v2", "base_url": base, "target": a.target, "started_at": now_iso("seconds"), "engine": a.engine,
           "build": f"v2-{client_v2.git_short_hash()}", "containers_before": containers(a.project)}

    probes: list[dict] = []
    stop = threading.Event()
    bad: dict[str, dict] = {}
    live: dict[str, tuple] = {}  # adversarial paper id -> owner, for the guard's cancel hook
    good_rec: dict = {}
    sc: dict = {}

    def cancel_bad() -> dict:
        stop.set()
        done = []
        for pid, owner in list(live.items()):
            try:
                owner.delete(f"/api/v2/papers/{pid}")
                done.append(pid)
            except Exception:
                pass
        return {"adversarial_papers_deleted": done}

    try:
        with Guard(base, "ROBUST", enabled=a.target == "jarvis",
                   prod_expected="stopped" if a.prod_stopped else "running", on_trip=[cancel_bad]) as guard:

            def probe():
                with httpx.Client(timeout=10) as c:
                    while not stop.is_set() and not guard.abort.is_set():
                        t = time.perf_counter()
                        try:
                            code = c.get(f"{base}/api/v2/health").status_code
                        except Exception as e:
                            code = f"{type(e).__name__}"
                        probes.append({"t": round(time.time(), 2), "status": code,
                                       "ms": round((time.perf_counter() - t) * 1000, 1)})
                        stop.wait(0.5)

            def good():
                path = make_fixtures.ensure(15)
                good_rec.update(client_v2.run_paper(path, a.engine, base_url=base, paper_id=path.stem, tag="ROBUST",
                                                    abort=guard.abort, segment_timeout_s=3600, ocsr_timeout_s=900))

            def submit(name, data):
                if guard.abort.is_set():
                    bad[name] = {"skipped": "guard tripped"}
                    return
                o = V2Owner(base)
                try:
                    r = post_paper(o, filename=f"{name}.pdf", data=data, engine=a.engine)
                    row = {"bytes": len(data), "upload_status": r.status_code, "upload_body": r.text[:300]}
                    if r.status_code < 300:
                        pid = r.json()["paper_id"]
                        live[pid] = o
                        d = wait_paper(o, pid, timeout_s=1800)
                        steps = o.get(f"/api/v2/papers/{pid}/steps").json()
                        row.update(paper_id=pid, status=d["status"], error=d.get("error"),
                                   failed_steps=[{k: st.get(k) for k in ("kind", "page", "status", "attempts",
                                                                         "error_class", "error")}
                                                 for st in steps.get("steps", steps)
                                                 if isinstance(st, dict) and st.get("status") == "failed"],
                                   steps_by_status=d["counts"]["steps_by_status"])
                        live.pop(pid, None)
                    bad[name] = row
                except Exception as e:
                    bad[name] = {"exception": f"{type(e).__name__}: {e}"[:400]}
                finally:
                    if not any(v is o for v in live.values()):
                        o.close()

            tp = threading.Thread(target=probe, daemon=True)
            tp.start()
            tg = threading.Thread(target=good)
            tg.start()
            time.sleep(3)
            ths = [threading.Thread(target=submit, args=(n, d)) for n, d in adversarial().items()]
            for t in ths:
                t.start()
            for t in ths:
                t.join()
            tg.join()
            time.sleep(2)
            stop.set()
            tp.join(timeout=15)
            res["guard"] = guard.summary()
            res["stopped_early"] = guard.tripped
    except GuardTripped as e:
        res["guard_refused"] = str(e)
        res["stopped_early"] = True

    meta = make_fixtures.load_meta(15)
    sc = fixture_accuracy.score(good_rec, meta) if good_rec.get("segments") is not None else {}
    bad_codes = [p for p in probes if p["status"] != 200]
    res.update({
        "finished_at": now_iso("seconds"),
        # client_v2 records no paper status; done = no fatal error and not aborted (M1)
        "good_paper": {"done": bool(good_rec) and good_rec.get("fatal_error") is None and not good_rec.get("aborted"),
                       "wall_s": round((good_rec.get("wall_ms") or 0) / 1000, 1),
                       "fatal_error": good_rec.get("fatal_error"), "failed_steps": good_rec.get("failed_steps"),
                       "page_errors": good_rec.get("page_errors"), "segments": sc.get("segments"),
                       "exact": sc.get("exact"), "skeleton": sc.get("skeleton"), "lost_pages": sc.get("lost_pages"),
                       "ocsr_cache_hits": good_rec.get("ocsr_cache_hits"), "v2_paper_id": good_rec.get("v2_paper_id")},
        "bad_papers": bad,
        "health": {"n": len(probes), "non_200": len(bad_codes), "non_200_samples": bad_codes[:50],
                   "max_ms": max((p["ms"] for p in probes), default=None)},
    })
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"{a.target}_v2_ROBUST_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
    out.write_text(json.dumps(res, indent=1, default=str))  # partial result first (M4)
    res["containers_after"] = containers(a.project)
    res["restarts"] = restarts(res["containers_before"], res["containers_after"])
    res["verdict"] = verdict(good_rec, sc, bad, bad_codes, res["restarts"])
    if res.get("stopped_early"):
        res["verdict"]["not_stopped_by_guard"] = False
    out.write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps({"good": res["good_paper"], "bad": {k: {kk: v.get(kk) for kk in ("upload_status", "status",
                      "failed_steps", "exception")} for k, v in bad.items()}, "health": res["health"]["non_200"],
                      "restarts": res["restarts"], "verdict": res["verdict"]}, indent=1, default=str))
    print(f"-> {out}")
    return 0 if all(res["verdict"].values()) else 1  # M3


if __name__ == "__main__":
    raise SystemExit(main())
