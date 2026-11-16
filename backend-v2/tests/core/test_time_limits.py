from marcus.core.enums import StepKind
from marcus.core.queues import TIME_LIMITS, time_limits_for


def test_docling_limits_scale_with_pages():
    assert time_limits_for(StepKind.DOCLING, None) == (300, 360)
    assert time_limits_for(StepKind.DOCLING, 15) == (300, 360)
    assert time_limits_for(StepKind.DOCLING, 100) == (1260, 1320)


def test_other_kinds_are_static():
    for kind, limits in TIME_LIMITS.items():
        if kind is not StepKind.DOCLING:
            assert time_limits_for(kind, 100) == limits
