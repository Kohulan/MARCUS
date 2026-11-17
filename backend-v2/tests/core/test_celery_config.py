import uuid

from marcus.core.enums import StepKind
from marcus.core.queues import QUEUE_WAIT_S, SLOTS, TIME_LIMITS
from marcus.core.settings import get_settings


def test_celery_config_values():
    from marcus.core.celery_app import celery_app

    conf = celery_app.conf
    assert conf.worker_prefetch_multiplier == 1
    assert conf.task_acks_late is True
    assert conf.task_reject_on_worker_lost is True
    assert conf.task_serializer == "json"
    assert list(conf.accept_content) == ["json"]
    assert conf.result_expires == 600
    assert conf.broker_connection_retry_on_startup is True
    assert conf.task_default_queue == "q.cpu"
    assert conf.broker_url == get_settings().redis_url
    assert conf.result_backend == get_settings().redis_url
    names = [q.name for q in conf.task_queues]
    assert sorted(names) == sorted([*SLOTS, "q.tools"])
    assert len(names) == len(set(names))


def test_run_step_registered_without_result():
    from marcus.core.celery_app import celery_app
    from marcus.workers import runtime

    task = celery_app.tasks["marcus.run_step"]
    assert task.name == runtime.run_step.name == "marcus.run_step"
    assert task.ignore_result is True


def test_dispatcher_send_uses_celery_app(monkeypatch):
    from marcus.core.celery_app import celery_app
    from marcus.dispatcher.__main__ import celery_send

    calls = []
    monkeypatch.setattr(celery_app, "send_task", lambda name, **kw: calls.append((name, kw)))
    step_id = uuid.uuid4()
    celery_send()("q.segment", step_id, StepKind.SEGMENT_PAGE, 1)

    soft, hard = TIME_LIMITS[StepKind.SEGMENT_PAGE]
    assert calls == [
        (
            "marcus.run_step",
            {
                "args": [str(step_id), 1],
                "queue": "q.segment",
                "soft_time_limit": soft,
                "time_limit": hard,
                "expires": QUEUE_WAIT_S["q.segment"],  # unserved messages expire (review I2)
            },
        )
    ]


def test_beat_start_logs_the_schedule(caplog):
    from marcus.core.celery_app import _log_beat_schedule

    with caplog.at_level("INFO", logger="marcus.core.celery_app"):
        _log_beat_schedule()
    assert "retention-purge-daily -> marcus.retention.purge_expired" in caplog.text
    assert "'queue': 'q.cpu'" in caplog.text
