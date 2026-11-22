"""The dispatcher's auto pass: annotation and R-group rows started by themselves, only where the
feature is on and a worker serves the queue; skipped quietly otherwise."""

import threading
import time

import pytest
from sqlalchemy import select

from marcus.core.models import Paper, RgroupExtraction, Step
from marcus.dispatcher.auto import BackgroundLiveQueues, auto_once
from tests.core.test_auto import _text_read_paper
from tests.core.test_rgroups_pipeline import done_paper

BOTH = frozenset({"q.cpu", "q.llm", "q.rgroup"})


@pytest.fixture
def features(monkeypatch, clear_settings_cache):
    def on(annotate: bool = True, rgroup: bool = True):
        monkeypatch.setenv("MARCUS_ANNOTATE_ENABLED", "1" if annotate else "0")
        monkeypatch.setenv("MARCUS_RGROUP_ENABLED", "1" if rgroup else "0")
        clear_settings_cache()

    return on


def _kinds(s) -> list[tuple[str, str]]:
    s.expire_all()
    return sorted((st.kind, st.status) for st in s.execute(select(Step)).scalars()
                  if st.kind in ("annotate", "rgroups"))  # fmt: skip


def _setup(s):
    """A done paper with a scaffold (its text read), committed: the pass runs its own
    transactions."""
    paper, scaffold, _ = done_paper(s)
    s.commit()
    return paper, scaffold


def test_both_start_by_themselves_and_the_paper_stays_done(db_session, features):
    s = db_session
    features()
    paper, scaffold = _setup(s)
    asked = []
    assert auto_once(s, lambda: asked.append(1) or BOTH) == 2
    assert _kinds(s) == [("annotate", "pending"), ("rgroups", "pending")]
    assert s.get(Paper, paper.id).status == "done"
    row = s.execute(select(RgroupExtraction)).scalar_one()
    assert row.prediction_id == scaffold.id and row.status == "queued"
    # asked once: the next pass finds nothing (and does not ask who serves the queues)
    assert auto_once(s, lambda: asked.append(1) or BOTH) == 0
    assert len(asked) == 1
    assert len(_kinds(s)) == 2


def test_a_feature_that_is_off_runs_nothing(db_session, features):
    s = db_session
    features(annotate=False, rgroup=False)
    _setup(s)
    assert auto_once(s, lambda: BOTH) == 0
    assert _kinds(s) == []


@pytest.mark.parametrize(
    ("live", "want"),
    [
        (frozenset({"q.cpu", "q.llm"}), [("annotate", "pending")]),
        (frozenset({"q.cpu", "q.rgroup"}), [("rgroups", "pending")]),
        (frozenset({"q.cpu"}), []),
        (None, []),  # who serves them is not known: nothing, tried again later
    ],
)
def test_a_queue_nobody_serves_is_skipped_quietly(db_session, features, live, want):
    s = db_session
    features()
    _setup(s)
    auto_once(s, lambda: live)
    assert _kinds(s) == want
    assert not s.execute(select(Step).where(Step.status == "failed")).first()


def test_only_the_annotation_where_r_groups_are_off(db_session, features):
    s = db_session
    features(rgroup=False)
    _setup(s)
    assert auto_once(s, lambda: BOTH) == 1
    assert _kinds(s) == [("annotate", "pending")]


def test_nothing_to_do_asks_no_one(db_session, features):
    s = db_session
    features()
    _text_read_paper(s, docling=False)
    s.commit()

    def boom():
        raise AssertionError("no consumer check without a candidate")

    assert auto_once(s, boom) == 0


def test_a_paper_deleted_meanwhile_is_skipped(db_session, features, monkeypatch):
    from marcus.core import auto
    from marcus.core.pipeline import cancel_paper

    s = db_session
    features(rgroup=False)
    paper, _ = _setup(s)
    found = auto.annotation_candidates(s)
    cancel_paper(s, paper.id, remove_files=False)
    s.commit()
    monkeypatch.setattr(auto, "annotation_candidates", lambda session: found)
    assert auto_once(s, lambda: BOTH) == 0
    assert _kinds(s) == []


# --- the consumer check without holding up the dispatcher ------------------------------------


def test_background_live_queues_never_waits_and_keeps_an_answer_for_a_while():
    gate = threading.Event()
    calls = []

    def probe():
        calls.append(1)
        gate.wait(2)
        return {"q.llm"}

    live = BackgroundLiveQueues(probe, ttl_s=60)
    start = time.monotonic()
    assert live() is None  # unknown at first: the broadcast runs in the background
    assert time.monotonic() - start < 0.5
    assert live() is None and len(calls) == 1  # one broadcast at a time
    gate.set()
    for _ in range(100):
        if live() == {"q.llm"}:
            break
        time.sleep(0.01)
    assert live() == {"q.llm"} and len(calls) == 1  # fresh: no second broadcast


def test_background_live_queues_asks_again_once_stale_and_a_failure_is_unknown():
    answers = iter([{"q.llm"}, {"q.rgroup"}])  # then StopIteration: a failed broadcast
    live = BackgroundLiveQueues(lambda: next(answers), ttl_s=0)
    seen = []
    for _ in range(300):
        value = live()
        if not seen or seen[-1] != value:
            seen.append(value)
        if len(seen) >= 4:
            break
        time.sleep(0.01)
    assert seen[:4] == [None, {"q.llm"}, {"q.rgroup"}, None]
