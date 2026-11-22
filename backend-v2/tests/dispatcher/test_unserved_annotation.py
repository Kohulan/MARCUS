"""An annotate step that cannot be served (no live q.llm consumer) does not wait for ever: after
`annotate_max_wait_s` the watchdog fails it (engine_error, final), so the annotation says failed
and its action is offered again (review I3, lead ruling). The step runs beside the paper's read:
the paper stays done throughout."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update

from marcus.core.models import Paper, Step
from marcus.core.pipeline import request_annotation
from marcus.core.settings import get_settings
from marcus.dispatcher.pick import watchdog_once
from tests.core.test_annotate_pipeline import _done_paper

LIVE_WITHOUT_LLM = frozenset({"q.cpu", "q.tools", "q.segment", "q.fake"})


def _annotating_paper(s, waited_s: float, status: str = "pending"):
    paper = _done_paper(s)
    step = request_annotation(s, paper.id)
    s.execute(
        update(Step)
        .where(Step.id == step.id)
        .values(
            created_at=datetime.now(UTC) - timedelta(seconds=waited_s),
            status=status,
            queued_at=datetime.now(UTC) if status == "queued" else None,
        )
    )
    s.commit()
    s.refresh(paper)
    assert paper.status == "done"  # beside the read: never reopened
    return paper, step


def _state(s, paper, step):
    s.expire_all()
    return s.get(Paper, paper.id).status, s.get(Step, step.id)


@pytest.mark.parametrize("status", ["pending", "queued"])
def test_an_annotate_step_that_cannot_be_served_fails(db_session, status):
    s = db_session
    limit = get_settings().annotate_max_wait_s
    paper, step = _annotating_paper(s, limit + 30, status)
    asked = []
    failed = watchdog_once(s, live_queues=lambda: asked.append(1) or LIVE_WITHOUT_LLM)
    assert failed == 1
    assert asked == [1]
    paper_status, row = _state(s, paper, step)
    assert row.status == "failed" and row.error_class == "engine_error"
    assert row.error == "no annotation worker"
    assert paper_status == "done"


def test_a_young_unserved_step_waits(db_session):
    s = db_session
    paper, step = _annotating_paper(s, get_settings().annotate_max_wait_s - 60)
    assert watchdog_once(s, live_queues=lambda: LIVE_WITHOUT_LLM) == 0
    paper_status, row = _state(s, paper, step)
    assert row.status == "pending" and paper_status == "done"


def test_an_old_step_on_a_served_queue_or_with_unknown_consumers_waits(db_session):
    s = db_session
    paper, step = _annotating_paper(s, get_settings().annotate_max_wait_s + 30)
    assert watchdog_once(s, live_queues=lambda: LIVE_WITHOUT_LLM | {"q.llm"}) == 0
    assert watchdog_once(s, live_queues=lambda: None) == 0  # broker down: not known
    assert watchdog_once(s) == 0  # no consumer check at all
    paper_status, row = _state(s, paper, step)
    assert row.status == "pending" and paper_status == "done"


def test_the_wait_is_a_setting(db_session, monkeypatch, clear_settings_cache):
    monkeypatch.setenv("MARCUS_ANNOTATE_MAX_WAIT_S", "60")
    clear_settings_cache()
    s = db_session
    paper, step = _annotating_paper(s, 90)
    assert watchdog_once(s, live_queues=lambda: LIVE_WITHOUT_LLM) == 1
    assert _state(s, paper, step)[0] == "done"
