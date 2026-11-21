"""Print Markdown tables from the newest load/results/<target>_<scenario>_*.json files.

    uv run python load/report.py            # all targets
    uv run python load/report.py jarvis     # one target
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RESULTS = Path(__file__).resolve().parent / "results"


def latest(target: str, scen: str):
    files = sorted(f for f in RESULTS.glob(f"{target}_{scen}_*.json") if not f.stem.endswith("_validation"))
    return json.loads(files[-1].read_text()) if files else None


def f(x, nd=1):
    return "-" if x is None else (f"{x:.{nd}f}" if isinstance(x, float) else str(x))


def s1(d):
    print("\n**S1 baseline** (15 structures alone)\n")
    print("| engine | warm-up call s | wall s | segmentation s | segments listed / OCSR'd | lost pages | OCSR p50 ms | OCSR p95 ms | page errors | recall (skeleton) | crash |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for eng, e in d["results"]["engines"].items():
        for r in e["runs"]:
            lp = r.get("lost_pages")
            wu = (e.get("warmup") or {}).get("ms")
            print(f"| {eng} | {f(wu / 1000 if wu else None)} | {f(r['wall_ms'] / 1000)} | {f((r['segment_ms'] or 0) / 1000)} | {r['segments_listed']} / {r['n_segments']} | "
                  f"{len(lp) if lp is not None else '-'} {lp or ''} | {f(r['ocsr_ms'].get('p50'), 0)} | {f(r['ocsr_ms'].get('p95'), 0)} | "
                  f"{len(r['page_errors'])} | {f(r.get('fixture_recall_skeleton'), 2)} | {r.get('backend_crash')} |")


def s2(d, title="S2 fairness"):
    r = d["results"]
    print(f"\n**{title}** (big = {r['big_structures']} structures, OCSR cap {r['big_ocsr_cap']}, engine {r['engine']})\n")
    print("| small paper | submitted at s | wall s | extract_segments s | OCSR p50 ms | OCSR p95 ms | slowdown vs S1 | ended during big run |")
    print("|---|---|---|---|---|---|---|---|")
    for i, s in enumerate(r["small"]):
        print(f"| #{i + 1} | {f(s['submitted_at_s'])} | {f(s['wall_ms'] / 1000)} | {f((s['extract_segments_ms'] or 0) / 1000)} | "
              f"{f(s['ocsr_ms'].get('p50'), 0)} | {f(s['ocsr_ms'].get('p95'), 0)} | {f(s['slowdown_vs_s1'], 1)} | {s['during_big_run']} |")
    b = r["big"] or {}
    print(f"\nbig paper: wall {f((b.get('wall_ms') or 0) / 1000)} s, segmentation {f((b.get('segment_ms') or 0) / 1000)} s; "
          f"health during S2 p50/p95/max ms: {r['health_probe']['ms_ok'].get('p50')}/{r['health_probe']['ms_ok'].get('p95')}/{r['health_probe']['ms_ok'].get('max')}")


def s3(d):
    r = d["results"]
    run = r["run"]
    print(f"\n**S3 responsiveness** (segmentation of {r['fixture']}, {d['summary']['segmentation_s']} s; "
          f"fatal: {run['fatal_error']}; backend crash: {run.get('backend_crash')}; page errors: {len(run['page_errors'])})\n")
    print("| probe | idle p95 ms | during p50 ms | during p95 ms | during max ms | probes during | errors | 429 |")
    print("|---|---|---|---|---|---|---|---|")
    for n, s in d["summary"].items():
        if isinstance(s, dict):
            print(f"| {n} | {f(s['idle_p95_ms'])} | {f(s['during_p50_ms'])} | {f(s['during_p95_ms'])} | {f(s['during_max_ms'])} | {s['during_n']} | {s['during_n_error']} | {s['during_n_429']} |")


def s4(d):
    r = d["results"]
    print(f"\n**S4 concurrency** (two-paper arms: {r['fixture']}, expected {r['expected_each']} segments each; "
          f"single-page arms: pages of synth_190, 8 expected each)\n")
    print("| arms | mode | repeat | wall s | sum of server 'took' s | segments found per paper | lost pages | page errors (layers) | error pages by batch of 4 | crash |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for a in r["arms"]:
        took = sum(a.get("server_segment_s") or [])
        lost = sum(len(p.get("lost_pages") or []) for p in a["papers"])
        layers = sorted({e.get("layer_type") or e.get("kind", "?") for e in a["page_errors"] or []})
        print(f"| {a.get('kind', 'two_papers')} | {a['mode']} | {a['repeat']} | {f(a['wall_s'])} | {f(took)} | {[p['segments_listed'] for p in a['papers']]} | {lost} | "
              f"{a['page_error_count']} {layers or ''} | {a['error_pages_by_batch4']} | {a.get('backend_crash')} |")
    if r.get("stopped"):
        print(f"\nstopped: {r['stopped']}")
    print("\n(sum of server 'took' close to wall = the backend processed the papers one after the other.)")


def s5(d):
    r = d["results"]
    print("\n**S5 script user** (generate_smiles with upload)\n")
    print("| phase | calls | ok | errors | 429 | p50 ms | p95 ms | max ms |")
    print("|---|---|---|---|---|---|---|---|")
    a = r["alone"]
    print(f"| alone | {a['n']} | {a['n_ok']} | {a['n_error']} | {a['n_429']} | {f(a['ms_ok'].get('p50'), 0)} | {f(a['ms_ok'].get('p95'), 0)} | {f(a['ms_ok'].get('max'), 0)} |")
    if "during_s2" in r:
        a = r["during_s2"]
        print(f"| during S2 | {a['n']} | {a['n_ok']} | {a['n_error']} | {a['n_429']} | {f(a['ms_ok'].get('p50'), 0)} | {f(a['ms_ok'].get('p95'), 0)} | {f(a['ms_ok'].get('max'), 0)} |")


def main():
    targets = sys.argv[1:] or ["local", "jarvis"]
    for t in targets:
        print(f"\n## {t}")
        for scen, fn in (("S1", s1), ("S2", s2), ("S2_2020", lambda d: s2(d, "S2 fairness, 2020-structure paper")),
                         ("S3", s3), ("S4", s4), ("S5", s5)):
            d = latest(t, scen)
            if d is None:
                continue
            note = " (STOPPED EARLY: " + str(d.get("guard", {}).get("trip_reason") or d.get("guard_refused")) + ")" if d.get("stopped_early") else ""
            if d.get("error"):
                note += f" (ERROR: {d['error']})"
            print(f"\n_{scen}: {d['started_at']}, {d['duration_s']} s{note}_")
            try:
                fn(d)
            except Exception as e:
                print(f"(could not render: {type(e).__name__}: {e})")


if __name__ == "__main__":
    main()
