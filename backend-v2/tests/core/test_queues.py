import importlib

import pytest

from marcus.core import queues
from marcus.core.enums import Engine, StepKind
from marcus.core.queues import SLOTS, TIME_LIMITS, queue_for

CASES = [
    (StepKind.CHECK_PDF, None, "q.cpu"),
    (StepKind.RENDER_PAGE, None, "q.cpu"),
    (StepKind.DOCLING, None, "q.cpu"),
    (StepKind.DOI, None, "q.cpu"),
    (StepKind.SEGMENT_PAGE, None, "q.segment"),
    (StepKind.OCSR, Engine.DECIMER, "q.decimer"),
    (StepKind.OCSR, Engine.DECIMER_HAND, "q.decimer"),
    (StepKind.OCSR, Engine.MOLNEXTR, "q.molnextr"),
    (StepKind.OCSR, Engine.MOLSCRIBE, "q.molscribe"),
    (StepKind.OCSR, Engine.FAKE, "q.fake"),
    (StepKind.ANNOTATE, None, "q.llm"),
    # its own queue: the R-group model has its own llama-server, so neither waits for the other
    (StepKind.RGROUPS, None, "q.rgroup"),
]


@pytest.mark.parametrize(("kind", "engine", "expected"), CASES)
def test_queue_for_every_kind_and_engine(kind, engine, expected):
    assert queue_for(kind, engine) == expected


def test_ocsr_requires_engine():
    with pytest.raises(ValueError):
        queue_for(StepKind.OCSR, None)


def test_slots_cover_all_queues_exactly():
    assert set(SLOTS) == {c[2] for c in CASES}
    assert SLOTS["q.cpu"] == 4
    assert all(v == 1 for k, v in SLOTS.items() if k != "q.cpu")


def test_slots_env_override(monkeypatch):
    monkeypatch.setenv("MARCUS_SLOTS_Q_CPU", "8")
    try:
        importlib.reload(queues)
        assert queues.SLOTS["q.cpu"] == 8
    finally:
        monkeypatch.undo()
        importlib.reload(queues)


def test_time_limits_cover_every_kind():
    assert set(TIME_LIMITS) == set(StepKind)
    assert TIME_LIMITS[StepKind.DOCLING] == (300, 360)
    assert TIME_LIMITS[StepKind.ANNOTATE] == (120, 150)
    assert all(s < h for s, h in TIME_LIMITS.values())


def test_queue_wait_covers_every_queue():
    """Queued steps wait up to QUEUE_WAIT_S[queue], independent of the run limit: model
    queues cover a worker (re)start with its model preload (decimer ~85-105 s on CPU)."""
    assert set(queues.QUEUE_WAIT_S) == set(SLOTS)
    for q in ("q.segment", "q.decimer", "q.molnextr", "q.molscribe", "q.llm", "q.rgroup"):
        assert queues.QUEUE_WAIT_S[q] == 300
    assert queues.QUEUE_WAIT_S["q.cpu"] == 120
    assert queues.QUEUE_WAIT_S["q.fake"] == 120


def test_queue_wait_env_override(monkeypatch):
    monkeypatch.setenv("MARCUS_QUEUE_WAIT_S_Q_DECIMER", "600")
    try:
        importlib.reload(queues)
        assert queues.QUEUE_WAIT_S["q.decimer"] == 600
        assert queues.QUEUE_WAIT_S["q.segment"] == 300
    finally:
        monkeypatch.undo()
        importlib.reload(queues)
