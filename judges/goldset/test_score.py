"""Unit tests for goldset/score.py on tiny hand-made cases.

    cd judges && uv run pytest goldset -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from chem import standardise  # noqa: E402
from score import score, sign_test_p, to_markdown  # noqa: E402

# L-alanine, D-alanine (stereo-only difference), ethanol, benzoic acid, sodium benzoate
L_ALA = "C[C@H](N)C(=O)O"
D_ALA = "C[C@@H](N)C(=O)O"
ETOH = "CCO"
BENZOIC = "OC(=O)c1ccccc1"
NA_BENZOATE = "[Na+].[O-]C(=O)c1ccccc1"


def exp(cid, smi):
    s = standardise(smi)
    return {"coconut_id": cid, "canonical_smiles": smi, "rdkit_ok": s.ok, "std_smiles": s.smiles,
            "inchikey": s.inchikey, "inchikey_first_block": s.first_block}


def paper(pid, smiles_list, split="dev"):
    return {"paper_id": pid, "split": split, "sha256": None,
            "expected": [exp(f"CNP{i}", s) for i, s in enumerate(smiles_list)]}


def run(pid, smiles, engine="decimer", build="v1", started="2026-01-01T00:00:00", page_errors=()):
    return {"paper_id": pid, "engine": engine, "build": build, "started_at": started,
            "page_errors": [{"page": p, "error": "x"} for p in page_errors],
            "segments": [{"segment_id": f"s{i}", "page": 1, "smiles": s, "error": None if s else "boom"}
                         for i, s in enumerate(smiles)]}


def pp(res, system="v1/decimer", pid="P1"):
    return res["per_paper"][system][pid]


def test_exact_match():
    res = score([paper("P1", [L_ALA, ETOH])], [run("P1", [ETOH, L_ALA])], n_boot=50)
    r = pp(res)
    assert r["recall_full"] == 1.0 and r["recall_first"] == 1.0
    assert r["best_tanimoto"] == pytest.approx(1.0)
    assert res["systems"]["v1/decimer"]["dev"]["recall_full"] == 1.0


def test_stereo_only_difference_counts_for_first_block_only():
    res = score([paper("P1", [L_ALA])], [run("P1", [D_ALA])], n_boot=50)
    r = pp(res)
    assert r["recall_full"] == 0.0
    assert r["recall_first"] == 1.0
    assert r["best_tanimoto"] == pytest.approx(1.0)  # Morgan FP ignores stereo


def test_partial_recall_and_salt_standardisation():
    res = score([paper("P1", [BENZOIC, ETOH])], [run("P1", [NA_BENZOATE])], n_boot=50)
    r = pp(res)
    assert r["recall_full"] == 0.5  # sodium benzoate -> benzoic acid after largest fragment + uncharge
    assert 0.0 <= r["best_tanimoto"] < 1.0


def test_invalid_smiles_counted_and_not_matched():
    res = score([paper("P1", [ETOH])], [run("P1", ["C1CC", "not a smiles", ETOH])], n_boot=50)
    r = pp(res)
    assert r["n_with_smiles"] == 3 and r["n_invalid"] == 2
    assert r["recall_full"] == 1.0
    assert res["systems"]["v1/decimer"]["dev"]["invalid_smiles_rate"] == pytest.approx(2 / 3)


def test_segment_error_without_smiles_is_not_invalid_smiles():
    res = score([paper("P1", [ETOH])], [run("P1", [None, ""])], n_boot=50)
    r = pp(res)
    assert r["n_segment_errors"] == 2 and r["n_invalid"] == 0 and r["recall_full"] == 0.0
    assert r["best_tanimoto"] == 0.0


def test_empty_run_scores_zero_and_missing_paper_listed():
    man = [paper("P1", [ETOH]), paper("P2", [BENZOIC])]
    res = score(man, [run("P1", [], page_errors=[2])], n_boot=50)
    s = res["systems"]["v1/decimer"]["dev"]
    assert pp(res)["recall_full"] == 0.0 and pp(res)["n_segments"] == 0
    assert s["papers_with_page_errors"] == 1 and s["papers_with_zero_segments"] == 1
    assert s["missing_papers"] == ["P2"] and s["n_papers"] == 1
    assert s["invalid_smiles_rate"] is None


def test_no_runs_at_all():
    res = score([paper("P1", [ETOH])], [], n_boot=50)
    assert res["systems"] == {}
    to_markdown(res)  # must not crash


def test_duplicate_predictions_do_not_inflate_recall():
    res = score([paper("P1", [ETOH, BENZOIC])], [run("P1", [ETOH, ETOH, "OCC", ETOH])], n_boot=50)
    r = pp(res)
    assert r["matched_full"] == 1 and r["recall_full"] == 0.5
    assert r["n_distinct_valid_predictions"] == 1


def test_duplicate_expected_structures_counted_once():
    # two COCONUT ids that standardise to the same molecule count as one expected structure
    res = score([paper("P1", [BENZOIC, NA_BENZOATE])], [run("P1", [BENZOIC])], n_boot=50)
    assert pp(res)["n_expected_full"] == 1 and pp(res)["recall_full"] == 1.0


def test_stereo_pair_counts_twice_full_once_first_block():
    res = score([paper("P1", [L_ALA, D_ALA])], [run("P1", [L_ALA])], n_boot=50)
    r = pp(res)
    assert (r["n_expected_full"], r["n_expected_first"]) == (2, 1)
    assert r["recall_full"] == 0.5 and r["recall_first"] == 1.0
    assert r["recall_full_grouped"] == 1.0  # one stereo record of the skeleton was hit exactly


def test_grouped_recall_needs_exact_stereo():
    res = score([paper("P1", [L_ALA])], [run("P1", ["CC(N)C(=O)O"])], n_boot=50)
    r = pp(res)
    assert r["recall_full_grouped"] == 0.0 and r["recall_first"] == 1.0


def test_duplicate_run_lines_keep_latest():
    runs = [run("P1", [ETOH], started="2026-01-02"), run("P1", [], started="2026-01-01")]
    res = score([paper("P1", [ETOH])], runs, n_boot=50)
    assert pp(res)["recall_full"] == 1.0
    assert any("duplicate" in w for w in res["warnings"])


def test_sha_mismatch_skipped():
    man = [dict(paper("P1", [ETOH]), sha256="a" * 64)]
    r = dict(run("P1", [ETOH]), pdf_sha256="b" * 64)
    res = score(man, [r], n_boot=50)
    assert res["systems"] == {} and len(res["sha_mismatch"]) == 1


def test_paired_comparison_and_splits():
    man = [paper("P1", [ETOH]), paper("P2", [BENZOIC]), paper("P3", [L_ALA], split="test")]
    runs = [run("P1", [ETOH], engine="a"), run("P2", [], engine="a"),
            run("P1", [ETOH], engine="b"), run("P2", [BENZOIC], engine="b"),
            run("P3", [L_ALA], engine="a")]
    res = score(man, runs, n_boot=200)
    cmp = res["paired"]["dev"]["v1/a vs v1/b"]
    assert cmp["n_papers"] == 2
    assert cmp["recall_full"]["mean_diff_b_minus_a"] == pytest.approx(0.5)
    assert (cmp["recall_full"]["b_better"], cmp["recall_full"]["ties"]) == (1, 1)
    assert res["paired"]["test"]["v1/a vs v1/b"]["n_papers"] == 0  # b did not run P3
    assert res["systems"]["v1/b"]["test"]["missing_papers"] == ["P3"]
    md = to_markdown(res)
    assert "Precision is not reported" in md


def test_bootstrap_is_deterministic_and_brackets_mean():
    man = [paper(f"P{i}", [ETOH]) for i in range(10)]
    runs = [run(f"P{i}", [ETOH] if i % 3 else []) for i in range(10)]
    a = score(man, runs, n_boot=500, seed=7)["systems"]["v1/decimer"]["dev"]
    b = score(man, runs, n_boot=500, seed=7)["systems"]["v1/decimer"]["dev"]
    assert a["recall_full_ci95"] == b["recall_full_ci95"]
    lo, hi = a["recall_full_ci95"]
    assert lo <= a["recall_full"] <= hi and lo < hi


def test_sign_test():
    assert sign_test_p(0, 0) == 1.0
    assert sign_test_p(10, 0) == pytest.approx(2 / 1024)
