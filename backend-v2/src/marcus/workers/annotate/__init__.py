"""Annotate package: importing it registers the `annotate` handler (worker-llm and, in the fake
stack, worker-fake-annotate: `celery ... --include marcus.workers.annotate`). A worker set to
the fake annotator stops at start where fake engines are disabled (a config error), never at
the first step."""

from marcus.core.settings import fake_enabled, get_settings
from marcus.workers.annotate import handler  # noqa: F401

if get_settings().annotator == "fake" and not fake_enabled():
    raise RuntimeError("the fake annotator is disabled (MARCUS_ENABLE_FAKE_ENGINES)")
