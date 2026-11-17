"""Offline tests for the fixture-accuracy gate scorer (load/fixture_accuracy.py: score), the robustness verdict
(load/robustness_v2.py) and the production-port refusal (common/target.py). No network, no docker."""
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "goldset"))

import chem  # noqa: E402
import fixture_accuracy  # noqa: E402
import robustness_v2  # noqa: E402
from common import target  # noqa: E402

ETHANOL, BENZENE, CAFFEINE = "CCO", "c1ccccc1", "CN1C=NC2=C1C(=O)N(C(=O)N2C)C"
LACTIC_L, LACTIC_D = "C[C@H](O)C(=O)O", "C[C@@H](O)C(=O)O"  # same skeleton, other stereo


def key(smiles):
    return chem.standardise(smiles).inchikey


def meta(*slots):
    """slots: (page, smiles) per expected structure, in index order; per_page counts from them."""
    pages = max(p for p, _ in slots) + 1
    per_page = [sum(1 for p, _ in slots if p == i) for i in range(pages)]
    return {"per_page": per_page,
            "expected": [{"index": i, "page": p, "slot": i, "inchikey": key(s)} for i, (p, s) in enumerate(slots)]}


def rec(*segs, listed_pages=None):
    """segs: (page, smiles); client_v1 and client_v2 both use the 0-based page index (sidecar numbering)."""
    return {"segments": [{"segment_id": f"page_{p}_{i}", "page": p, "smiles": s, "error": None}
                         for i, (p, s) in enumerate(segs)],
            "listed_pages": sorted({p for p, _ in segs}) if listed_pages is None else listed_pages}


def test_exact_match_is_page_local_and_zero_based():
    m = meta((0, ETHANOL), (1, BENZENE))
    sc = fixture_accuracy.score(rec((0, ETHANOL), (1, BENZENE)), m)
    assert sc["exact"] == 2 and sc["exact_slots"] == [0, 1] and sc["exact_rate"] == 1.0
    # the same predictions one page off (a 1-based page index) match nothing
    off = fixture_accuracy.score(rec((1, ETHANOL), (2, BENZENE)), m)
    assert off["exact"] == 0 and off["skeleton"] == 0


def test_right_molecule_on_another_page_does_not_count():
    m = meta((0, ETHANOL), (1, CAFFEINE))
    sc = fixture_accuracy.score(rec((0, CAFFEINE), (1, ETHANOL)), m)
    assert sc["exact"] == 0


def test_duplicate_prediction_counts_once_per_slot():
    m = meta((0, ETHANOL), (0, BENZENE))
    sc = fixture_accuracy.score(rec((0, ETHANOL), (0, ETHANOL), (0, ETHANOL)), m)
    assert sc["exact"] == 1 and sc["exact_slots"] == [0] and sc["segments"] == 3 and sc["valid_smiles"] == 3


def test_stereo_error_is_skeleton_only():
    m = meta((0, LACTIC_L))
    sc = fixture_accuracy.score(rec((0, LACTIC_D)), m)
    assert sc["exact"] == 0 and sc["skeleton"] == 1


def test_invalid_and_empty_smiles_never_match():
    m = meta((0, ETHANOL))
    sc = fixture_accuracy.score(rec((0, "C1CC"), (0, "")), m)
    assert sc["exact"] == 0 and sc["valid_smiles"] == 0
    assert [r["inchikey"] for r in sc["seg_rows"]] == [None, None]


def test_lost_pages_are_pages_with_structures_but_no_segment():
    m = meta((0, ETHANOL), (1, BENZENE), (2, CAFFEINE))
    sc = fixture_accuracy.score(rec((0, ETHANOL), (2, CAFFEINE)), m)
    assert sc["lost_pages"] == [1] and sc["exact"] == 2
    # a page the server listed counts as found even when no segment row came back for it (OCSR-capped runs)
    listed = fixture_accuracy.score(rec((0, ETHANOL), listed_pages=[0, 1, 2]), m)
    assert listed["lost_pages"] == []
    # a crashed run: no segments at all, every page with structures is lost
    crash = fixture_accuracy.score({"segments": [], "listed_pages": None}, m)
    assert crash["lost_pages"] == [0, 1, 2] and crash["exact"] == 0 and crash["expected"] == 3


def test_page_without_structures_is_never_lost():
    m = {"per_page": [1, 0], "expected": [{"index": 0, "page": 0, "slot": 0, "inchikey": key(ETHANOL)}]}
    assert fixture_accuracy.score(rec((0, ETHANOL)), m)["lost_pages"] == []


# --- robustness verdict --------------------------------------------------------------------------------------------

GOOD = {"fatal_error": None, "aborted": False}
SC15 = {"segments": 15, "lost_pages": []}


def test_robust_verdict_all_good():
    bad = {"a": {"upload_status": 415}, "b": {"upload_status": 202, "status": "failed"},
           "c": {"upload_status": 202, "status": "done"}}
    assert all(robustness_v2.verdict(GOOD, SC15, bad, [], {}).values())


def test_robust_verdict_5xx_upload_is_not_a_clean_refusal():
    v = robustness_v2.verdict(GOOD, SC15, {"a": {"upload_status": 500}}, [], {})
    assert v["every_bad_paper_failed_or_rejected_alone"] is False


@pytest.mark.parametrize("good,sc,codes,restarted,flag", [
    ({"fatal_error": "PaperFailed", "aborted": False}, SC15, [], {}, "good_paper_done_all_15"),
    (GOOD, {"segments": 15, "lost_pages": [2]}, [], {}, "good_paper_done_all_15"),
    (GOOD, SC15, [{"status": 502}], {}, "api_health_always_200"),
    (GOOD, SC15, [], {"marcus-v2-test-worker-segment-1": 1}, "no_container_restart"),
])
def test_robust_verdict_flags(good, sc, codes, restarted, flag):
    assert robustness_v2.verdict(good, sc, {}, codes, restarted)[flag] is False


def test_restarts_ignore_unchanged_and_count_new_starts():
    before = {"w": {"restart_count": 0, "started_at": "t0"}, "x": {"restart_count": 1, "started_at": "t1"}}
    after = {"w": {"restart_count": 0, "started_at": "t0", "status": "running"},
             "x": {"restart_count": 2, "started_at": "t2", "status": "running"},
             "gone:abc": {"restart_count": None, "started_at": None, "status": "gone"}}
    assert robustness_v2.restarts(before, after) == {"x": 1, "gone:abc": 0}
    assert robustness_v2.restarts(before, {"w": after["w"]}) == {"x": "missing after the run"}


# --- production ports ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("url", ["http://127.0.0.1:9000", "http://localhost:8080/", "http://127.0.0.1:9000/health",
                                 "http://[::1]:9000", "http://0.0.0.0:8080", "http://127.0.1.1:9000"])
def test_production_ports_on_loopback_are_refused(url):
    with pytest.raises(SystemExit, match="8080 and 9000"):
        target._check(url)


@pytest.mark.parametrize("url", ["http://127.0.0.1:18090", "http://localhost:19000", "http://127.0.0.1:29000",
                                 "http://localhost:18080", "http://localhost:29090"])
def test_judge_ports_are_allowed(url):
    assert target._check(url) == url


def test_production_hosts_still_refused():
    for url in ("https://marcus.decimer.ai", "http://jarvis.ian.uni-jena.de:18090", "http://jarvis:19000"):
        with pytest.raises(SystemExit, match="production host"):
            target._check(url)
