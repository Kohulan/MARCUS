"""Score MARCUS run JSONL files against the gold-set manifest.

    cd judges && uv run python goldset/score.py runs/*.jsonl \
        --manifest goldset/manifest.jsonl --out goldset/score.json --md goldset/score.md

A "system" is one (build, engine) pair, e.g. v1-976396a5/decimer. Every
system is scored per split (dev/test) on the same metrics, and every pair of
systems is compared paper-by-paper on the papers both ran.

Metrics (all per paper, then averaged over papers = macro):
  recall_full   share of the paper's expected structures (distinct full
                InChIKeys after standardisation) that appear among the
                standardised predictions of that paper.
  recall_full_grouped
                expected structures grouped by InChIKey first block; a group
                counts as found if ANY of its full keys was predicted.
                COCONUT often holds several stereo records for one compound
                (from different source collections), so strict recall_full
                cannot reach 100% on those papers; this variant can.
  recall_first  same with InChIKey first block (connectivity only: stereo,
                isotopes and protonation layer ignored).
  best_tanimoto mean over expected structures of the max Morgan(r=2, 2048)
                Tanimoto against all valid predictions in the paper (0 when
                the paper has no valid prediction).
Precision is NOT reported: papers show many structures COCONUT does not list
(synthetic intermediates, known reference compounds, reagents), so an
unmatched prediction is not evidence of an error.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from chem import STANDARDISATION, fingerprint, standardise, tanimoto  # noqa: E402

PRECISION_NOTE = (
    "Precision is not reported. COCONUT lists only the natural products it "
    "links to a DOI; the papers also draw intermediates, known reference "
    "compounds, reagents and partial structures, so a prediction that matches "
    "nothing in COCONUT is not necessarily wrong."
)
N_BOOT = 2000
SEED = 12345


# ---- loading ----------------------------------------------------------------
def load_jsonl(path: Path) -> list[dict]:
    out = []
    with path.open() as f:
        for ln, line in enumerate(f, 1):
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise SystemExit(f"{path}:{ln}: bad JSON: {exc}") from exc
    return out


def system_of(run: dict) -> str:
    return f"{run.get('build', '?')}/{run.get('engine', '?')}"


# ---- per paper --------------------------------------------------------------
def expected_sets(paper: dict) -> tuple[set[str], set[str], list[str]]:
    """Distinct full keys, distinct first blocks, and std SMILES for Tanimoto (one per full key)."""
    full: set[str] = set()
    first: set[str] = set()
    smiles_by_key: dict[str, str] = {}
    for e in paper["expected"]:
        if not e.get("rdkit_ok") or not e.get("inchikey"):
            continue
        full.add(e["inchikey"])
        first.add(e["inchikey"].split("-")[0])
        smiles_by_key.setdefault(e["inchikey"], e["std_smiles"])
    return full, first, [smiles_by_key[k] for k in sorted(smiles_by_key)]


def score_paper(paper: dict, run: dict) -> dict:
    exp_full, exp_first, exp_smiles = expected_sets(paper)
    segments = run.get("segments") or []
    n_with_smiles = n_invalid = n_seg_error = n_no_key = 0
    pred_full: set[str] = set()
    pred_first: set[str] = set()
    pred_fps = []
    seen_std: set[str] = set()
    for seg in segments:
        smi = seg.get("smiles")
        if seg.get("error") and not smi:
            n_seg_error += 1
            continue
        if not isinstance(smi, str) or not smi.strip():
            n_seg_error += 1  # no output and no error text: still a failed segment
            continue
        n_with_smiles += 1
        s = standardise(smi)
        if not s.ok:
            n_invalid += 1
            continue
        if s.inchikey:
            pred_full.add(s.inchikey)
            pred_first.add(s.first_block)
        else:
            n_no_key += 1  # parses but InChI fails, e.g. '*' / R-group atoms
        if s.smiles not in seen_std:
            seen_std.add(s.smiles)
            fp = fingerprint(s.smiles)
            if fp is not None:
                pred_fps.append(fp)
    hit_full = exp_full & pred_full
    hit_first = exp_first & pred_first
    # grouped: a skeleton counts as found with stereo if ANY of the COCONUT
    # stereo records sharing that first block was predicted exactly.
    groups: dict[str, set[str]] = defaultdict(set)
    for k in exp_full:
        groups[k.split("-")[0]].add(k)
    hit_grouped = sum(1 for keys in groups.values() if keys & pred_full)
    best = [tanimoto(fingerprint(smi), pred_fps) for smi in exp_smiles]
    page_errors = run.get("page_errors") or []
    return {
        "paper_id": paper["paper_id"],
        "n_expected_full": len(exp_full),
        "n_expected_first": len(exp_first),
        "matched_full": len(hit_full),
        "matched_first": len(hit_first),
        "recall_full": len(hit_full) / len(exp_full) if exp_full else None,
        "recall_first": len(hit_first) / len(exp_first) if exp_first else None,
        "matched_full_grouped": hit_grouped,
        "recall_full_grouped": hit_grouped / len(groups) if groups else None,
        "best_tanimoto": statistics.fmean(best) if best else None,
        "matched_keys": sorted(hit_full),
        "n_segments": len(segments),
        "n_with_smiles": n_with_smiles,
        "n_invalid": n_invalid,
        "n_valid_no_inchikey": n_no_key,
        "n_segment_errors": n_seg_error,
        "n_distinct_valid_predictions": len(seen_std),
        "n_page_errors": len(page_errors),
        "pages_total": run.get("pages_total"),
        "wall_ms": run.get("wall_ms"),
    }


# ---- statistics ---------------------------------------------------------------
def bootstrap_ci(values: list[float], n_boot: int, seed: int) -> list[float] | None:
    v = np.asarray([x for x in values if x is not None], dtype=float)
    if len(v) == 0:
        return None
    if len(v) == 1:
        return [float(v[0]), float(v[0])]
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(v), size=(n_boot, len(v)))
    means = v[idx].mean(axis=1)
    return [float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))]


def bootstrap_ratio_ci(num: list[int], den: list[int], n_boot: int, seed: int) -> list[float] | None:
    """CI for a pooled (micro) ratio, resampling papers."""
    a, b = np.asarray(num, float), np.asarray(den, float)
    if len(a) == 0 or b.sum() == 0:
        return None
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(a), size=(n_boot, len(a)))
    with np.errstate(invalid="ignore", divide="ignore"):
        r = a[idx].sum(axis=1) / b[idx].sum(axis=1)
    r = r[~np.isnan(r)]
    return [float(np.percentile(r, 2.5)), float(np.percentile(r, 97.5))]


def sign_test_p(wins: int, losses: int) -> float:
    """Exact two-sided sign test (ties dropped)."""
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * p)


def mean_or_none(xs):
    xs = [x for x in xs if x is not None]
    return statistics.fmean(xs) if xs else None


def summarise(rows: list[dict], n_boot: int, seed: int) -> dict:
    rf = [r["recall_full"] for r in rows]
    r1 = [r["recall_first"] for r in rows]
    rg = [r["recall_full_grouped"] for r in rows]
    bt = [r["best_tanimoto"] for r in rows]
    seg = [r["n_segments"] for r in rows]
    n_pred = sum(r["n_with_smiles"] for r in rows)
    n_inv = sum(r["n_invalid"] for r in rows)
    n_segs = sum(seg)
    return {
        "n_papers": len(rows),
        "recall_full": mean_or_none(rf),
        "recall_full_ci95": bootstrap_ci(rf, n_boot, seed),
        "recall_full_grouped": mean_or_none(rg),
        "recall_full_grouped_ci95": bootstrap_ci(rg, n_boot, seed),
        "recall_first": mean_or_none(r1),
        "recall_first_ci95": bootstrap_ci(r1, n_boot, seed),
        "micro_recall_full": (sum(r["matched_full"] for r in rows) / max(1, sum(r["n_expected_full"] for r in rows))),
        "micro_recall_full_ci95": bootstrap_ratio_ci([r["matched_full"] for r in rows],
                                                     [r["n_expected_full"] for r in rows], n_boot, seed),
        "micro_recall_first": (sum(r["matched_first"] for r in rows) / max(1, sum(r["n_expected_first"] for r in rows))),
        "mean_best_tanimoto": mean_or_none(bt),
        "mean_best_tanimoto_ci95": bootstrap_ci(bt, n_boot, seed),
        "papers_with_full_recall_1": sum(1 for x in rf if x == 1.0),
        "papers_with_zero_recall_full": sum(1 for x in rf if x == 0.0),
        "predictions_with_smiles": n_pred,
        "invalid_smiles": n_inv,
        "invalid_smiles_rate": (n_inv / n_pred) if n_pred else None,
        "valid_without_inchikey": sum(r["n_valid_no_inchikey"] for r in rows),
        "segment_errors": sum(r["n_segment_errors"] for r in rows),
        "segment_error_rate": (sum(r["n_segment_errors"] for r in rows) / n_segs) if n_segs else None,
        "papers_with_page_errors": sum(1 for r in rows if r["n_page_errors"] > 0),
        "papers_with_zero_segments": sum(1 for s in seg if s == 0),
        "segments_per_paper": ({"mean": statistics.fmean(seg), "median": statistics.median(seg),
                                "max": max(seg), "total": n_segs} if seg else None),
    }


def paired(rows_a: dict[str, dict], rows_b: dict[str, dict], n_boot: int, seed: int) -> dict:
    common = sorted(set(rows_a) & set(rows_b))
    out: dict = {"n_papers": len(common)}
    for metric in ("recall_full", "recall_full_grouped", "recall_first", "best_tanimoto"):
        diffs = [rows_b[p][metric] - rows_a[p][metric] for p in common
                 if rows_a[p][metric] is not None and rows_b[p][metric] is not None]
        wins = sum(d > 0 for d in diffs)
        losses = sum(d < 0 for d in diffs)
        out[metric] = {
            "mean_diff_b_minus_a": statistics.fmean(diffs) if diffs else None,
            "ci95": bootstrap_ci(diffs, n_boot, seed),
            "b_better": wins, "a_better": losses, "ties": len(diffs) - wins - losses,
            "sign_test_p": sign_test_p(wins, losses),
        }
    return out


# ---- top level ----------------------------------------------------------------
def score(manifest: list[dict], runs: list[dict], *, n_boot: int = N_BOOT, seed: int = SEED) -> dict:
    papers = {p["paper_id"]: p for p in manifest}
    warnings: list[str] = []
    # latest run per (system, paper)
    chosen: dict[tuple[str, str], dict] = {}
    duplicates = 0
    unknown = 0
    sha_mismatch: list[dict] = []
    for run in runs:
        pid = run.get("paper_id")
        if pid not in papers:
            unknown += 1
            continue
        want = papers[pid].get("sha256")
        if want and run.get("pdf_sha256") and run["pdf_sha256"] != want:
            sha_mismatch.append({"system": system_of(run), "paper_id": pid})
            continue
        k = (system_of(run), pid)
        if k in chosen:
            duplicates += 1
            if str(run.get("started_at", "")) < str(chosen[k].get("started_at", "")):
                continue
        chosen[k] = run
    if unknown:
        warnings.append(f"{unknown} run line(s) for paper_ids not in the manifest were ignored")
    if duplicates:
        warnings.append(f"{duplicates} duplicate (system, paper) run line(s); the latest started_at was kept")
    if sha_mismatch:
        warnings.append(f"{len(sha_mismatch)} run line(s) skipped: pdf_sha256 differs from manifest")

    per_paper: dict[str, dict[str, dict]] = defaultdict(dict)
    for (system, pid), run in sorted(chosen.items()):
        per_paper[system][pid] = score_paper(papers[pid], run)

    splits = sorted({p["split"] for p in manifest})
    systems = sorted(per_paper)
    result: dict = {
        "standardisation": STANDARDISATION,
        "precision": PRECISION_NOTE,
        "bootstrap": {"n_resamples": n_boot, "seed": seed, "unit": "paper", "ci": "percentile 95%"},
        "warnings": warnings,
        "sha_mismatch": sha_mismatch,
        "manifest_papers": {s: sum(p["split"] == s for p in manifest) for s in splits},
        "expected_excluded_rdkit_failed": sum(1 for p in manifest for e in p["expected"]
                                              if not e.get("rdkit_ok") or not e.get("inchikey")),
        "systems": {},
        "paired": {},
        "per_paper": per_paper,
    }
    for system in systems:
        result["systems"][system] = {}
        for split in splits:
            ids = [pid for pid, p in papers.items() if p["split"] == split]
            rows = [per_paper[system][pid] for pid in ids if pid in per_paper[system]]
            summ = summarise(rows, n_boot, seed)
            summ["n_manifest_papers"] = len(ids)
            summ["missing_papers"] = sorted(pid for pid in ids if pid not in per_paper[system])
            result["systems"][system][split] = summ
    for split in splits:
        ids = {pid for pid, p in papers.items() if p["split"] == split}
        for a, b in itertools.combinations(systems, 2):
            ra = {k: v for k, v in per_paper[a].items() if k in ids}
            rb = {k: v for k, v in per_paper[b].items() if k in ids}
            result["paired"].setdefault(split, {})[f"{a} vs {b}"] = paired(ra, rb, n_boot, seed)
    return result


def _f(x, pct=True):
    if x is None:
        return "n/a"
    return f"{100 * x:.1f}" if pct else f"{x:.3f}"


def _ci(ci, pct=True):
    if not ci:
        return ""
    return f" [{_f(ci[0], pct)}, {_f(ci[1], pct)}]"


def to_markdown(res: dict) -> str:
    L = ["# MARCUS gold-set score", "",
         ("Recall in %, macro (mean over papers) with paper-level bootstrap 95% CI. "
          "Full = full InChIKey; skeleton = InChIKey first block (stereo-agnostic)."), "",
         f"> {res['precision']}", ""]
    for w in res["warnings"]:
        L.append(f"- warning: {w}")
    if res["warnings"]:
        L.append("")
    L += [("| split | system | papers run/total | recall full | recall skeleton | micro recall full | "
           "recall full grouped | mean best Tanimoto | invalid SMILES % | papers w/ page errors | segments/paper median (max) |"),
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for system, by_split in res["systems"].items():
        for split, s in by_split.items():
            seg = s["segments_per_paper"]
            L.append(
                f"| {split} | {system} | {s['n_papers']}/{s['n_manifest_papers']} | "
                f"{_f(s['recall_full'])}{_ci(s['recall_full_ci95'])} | "
                f"{_f(s['recall_first'])}{_ci(s['recall_first_ci95'])} | "
                f"{_f(s['micro_recall_full'])} | "
                f"{_f(s['recall_full_grouped'])}{_ci(s['recall_full_grouped_ci95'])} | "
                f"{_f(s['mean_best_tanimoto'], False)}{_ci(s['mean_best_tanimoto_ci95'], False)} | "
                f"{_f(s['invalid_smiles_rate'])} | {s['papers_with_page_errors']} | "
                f"{(str(seg['median']) + ' (' + str(seg['max']) + ')') if seg else 'n/a'} |")
    if any(res["paired"].values()):
        L += ["", "## Paired comparison (same papers; diff = B - A, recall in points)", "",
              ("| split | A vs B | papers | diff recall full [CI] | B better / A better / tie | sign p | "
               "diff recall skeleton [CI] |"), "|---|---|---|---|---|---|---|"]
        for split, pairs in res["paired"].items():
            for name, p in pairs.items():
                f, s1 = p["recall_full"], p["recall_first"]
                L.append(f"| {split} | {name} | {p['n_papers']} | {_f(f['mean_diff_b_minus_a'])}{_ci(f['ci95'])} | "
                         f"{f['b_better']} / {f['a_better']} / {f['ties']} | {f['sign_test_p']:.3g} | "
                         f"{_f(s1['mean_diff_b_minus_a'])}{_ci(s1['ci95'])} |")
    return "\n".join(L) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="+", type=Path, help="run JSONL file(s)")
    ap.add_argument("--manifest", type=Path, default=Path(__file__).resolve().parent / "manifest.jsonl")
    ap.add_argument("--out", type=Path, help="write full JSON here (default: stdout)")
    ap.add_argument("--md", type=Path, help="write markdown table here (default: stderr)")
    ap.add_argument("--n-boot", type=int, default=N_BOOT)
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args()
    manifest = load_jsonl(args.manifest)
    runs = [r for p in args.runs for r in load_jsonl(p)]
    res = score(manifest, runs, n_boot=args.n_boot, seed=args.seed)
    js = json.dumps(res, indent=1)
    md = to_markdown(res)
    if args.out:
        args.out.write_text(js + "\n")
    else:
        print(js)
    if args.md:
        args.md.write_text(md)
    else:
        print(md, file=sys.stderr)


if __name__ == "__main__":
    main()
