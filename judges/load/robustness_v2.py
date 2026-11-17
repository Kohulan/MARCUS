"""Robustness on v2 (spec §3 "Robust"): a bad PDF fails only its own paper, no worker crash takes the API down,
0 lost pages on the S1 fixture.

    cd judges
    uv run python load/robustness_v2.py --base-url http://127.0.0.1:18090 --project marcus-v2-test

One good paper (synth_015, 15 structures, engine decimer) starts first; 3 s later every adversarial PDF is uploaded
at once, each by its own owner: the security judge's two payloads (security/payloads.py: garbage %PDF header, XSS
text), the backend's adversarial fixtures (encrypted, zero pages, a PNG named .pdf) and three made here (synth_015
cut in half, a 200x200-inch page whose 300 dpi render would be 60000x60000 px, a page with a 1 GB flate bomb).
While they run, GET /api/v2/health is probed every 0.5 s. Recorded: every paper's final status and failed steps,
the good paper's segments and exact matches against the fixture sidecar, the health probes, and the docker
RestartCount / state of every container of the project before and after (read-only docker inspect).
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
from datetime import datetime, timezone
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
from v2.helpers import V2Owner, post_paper, wait_paper  # noqa: E402

RESULTS = HERE / "results"
BACKEND_PDFS = ROOT.parent / "backend-v2" / "tests" / "fixtures" / "pdfs"


def utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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
    ids = subprocess.run(["docker", "ps", "-a", "-q", "--filter", f"label=com.docker.compose.project={project}"],
                         capture_output=True, text=True, timeout=30).stdout.split()
    out = {}
    for cid in ids:
        f = "{{.Name}}|{{.RestartCount}}|{{.State.Status}}|{{.State.StartedAt}}|{{.State.OOMKilled}}"
        name, rc, st, started, oom = subprocess.run(["docker", "inspect", "-f", f, cid], capture_output=True,
                                                    text=True, timeout=30).stdout.strip().split("|")
        out[name.lstrip("/")] = {"restart_count": int(rc), "status": st, "started_at": started, "oom_killed": oom}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--project", required=True, help="compose project of the test stack (docker inspect, read-only)")
    ap.add_argument("--engine", default="decimer")
    ap.add_argument("--target", default="jarvis")
    a = ap.parse_args(argv)
    base = target._check(a.base_url.rstrip("/"))
    res = {"kind": "robustness_v2", "base_url": base, "started_at": utc(), "engine": a.engine,
           "containers_before": containers(a.project)}

    probes: list[dict] = []
    stop = threading.Event()

    def probe():
        with httpx.Client(timeout=10) as c:
            while not stop.is_set():
                t = time.perf_counter()
                try:
                    code = c.get(f"{base}/api/v2/health").status_code
                except Exception as e:
                    code = f"{type(e).__name__}"
                probes.append({"t": round(time.time(), 2), "status": code, "ms": round((time.perf_counter() - t) * 1000, 1)})
                stop.wait(0.5)

    good_rec: dict = {}

    def good():
        path = make_fixtures.ensure(15)
        good_rec.update(client_v2.run_paper(path, a.engine, base_url=base, paper_id=path.stem, tag="ROBUST",
                                            segment_timeout_s=3600, ocsr_timeout_s=900))

    tp = threading.Thread(target=probe, daemon=True)
    tp.start()
    tg = threading.Thread(target=good)
    tg.start()
    time.sleep(3)

    bad: dict[str, dict] = {}

    def submit(name, data):
        o = V2Owner(base)
        try:
            r = post_paper(o, filename=f"{name}.pdf", data=data, engine=a.engine)
            row = {"bytes": len(data), "upload_status": r.status_code, "upload_body": r.text[:300]}
            if r.status_code < 300:
                pid = r.json()["paper_id"]
                d = wait_paper(o, pid, timeout_s=1800)
                steps = o.get(f"/api/v2/papers/{pid}/steps").json()
                row.update(paper_id=pid, status=d["status"], error=d.get("error"),
                           failed_steps=[{k: s.get(k) for k in ("kind", "page", "status", "attempts", "error_class",
                                                                "error")} for s in steps.get("steps", steps)
                                         if isinstance(s, dict) and s.get("status") == "failed"],
                           steps_by_status=d["counts"]["steps_by_status"])
            bad[name] = row
        except Exception as e:
            bad[name] = {"exception": f"{type(e).__name__}: {e}"[:400]}
        finally:
            o.close()

    ths = [threading.Thread(target=submit, args=(n, d)) for n, d in adversarial().items()]
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    tg.join()
    time.sleep(2)
    stop.set()
    tp.join(timeout=15)

    meta = make_fixtures.load_meta(15)
    sc = fixture_accuracy.score(good_rec, meta) if good_rec.get("segments") is not None else {}
    bad_codes = [p for p in probes if p["status"] != 200]
    res.update({
        "finished_at": utc(),
        "good_paper": {"status": good_rec.get("status"), "wall_s": round((good_rec.get("wall_ms") or 0) / 1000, 1),
                       "fatal_error": good_rec.get("fatal_error"), "failed_steps": good_rec.get("failed_steps"),
                       "page_errors": good_rec.get("page_errors"), "segments": sc.get("segments"),
                       "exact": sc.get("exact"), "skeleton": sc.get("skeleton"), "lost_pages": sc.get("lost_pages"),
                       "ocsr_cache_hits": good_rec.get("ocsr_cache_hits"), "v2_paper_id": good_rec.get("v2_paper_id")},
        "bad_papers": bad,
        "health": {"n": len(probes), "non_200": len(bad_codes), "non_200_samples": bad_codes[:50],
                   "max_ms": max((p["ms"] for p in probes), default=None)},
        "containers_after": containers(a.project),
    })
    before, after = res["containers_before"], res["containers_after"]
    res["restarts"] = {n: after[n]["restart_count"] - before.get(n, {}).get("restart_count", 0)
                       for n in after if after[n]["restart_count"] != before.get(n, {}).get("restart_count", 0)
                       or after[n]["started_at"] != before.get(n, {}).get("started_at")}
    res["verdict"] = {
        "good_paper_done_all_15": bool(sc) and sc.get("segments") == 15 and not sc.get("lost_pages")
        and good_rec.get("fatal_error") is None,
        "every_bad_paper_failed_or_rejected_alone": all(
            (b.get("upload_status", 0) >= 400) or b.get("status") in ("failed", "done") for b in bad.values()),
        "api_health_always_200": not bad_codes,
        "no_container_restart": not res["restarts"],
    }
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"{a.target}_v2_ROBUST_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
    out.write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps({"good": res["good_paper"], "bad": {k: {kk: v.get(kk) for kk in ("upload_status", "status",
                      "failed_steps", "exception")} for k, v in bad.items()}, "health": res["health"]["non_200"],
                      "restarts": res["restarts"], "verdict": res["verdict"]}, indent=1, default=str))
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
