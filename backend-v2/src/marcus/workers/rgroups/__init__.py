"""R-group package: importing it registers the `rgroups` handler (worker-llm and, in the fake
stack, worker-fake-annotate: `celery ... --include marcus.workers.annotate,marcus.workers.rgroups`).
A worker set to the fake reader stops at start where fake engines are disabled (a config error),
never at the first step."""

from marcus.core.settings import fake_enabled, get_settings
from marcus.workers.rgroups import handler  # noqa: F401

if get_settings().rgroup_reader == "fake" and not fake_enabled():
    raise RuntimeError("the fake R-group reader is disabled (MARCUS_ENABLE_FAKE_ENGINES)")
