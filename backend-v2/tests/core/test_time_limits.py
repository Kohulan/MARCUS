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


def test_decimer_hand_ocsr_has_its_own_limits():
    """decimer-hand loads its model on its first request (~76 s on CPU, measured in B2): only
    its ocsr steps get the longer limit."""
    from marcus.core.enums import Engine
    from marcus.core.queues import ENGINE_TIME_LIMITS

    hand = time_limits_for(StepKind.OCSR, None, Engine.DECIMER_HAND)
    assert hand == ENGINE_TIME_LIMITS[(StepKind.OCSR, Engine.DECIMER_HAND)] == (180, 210)
    assert time_limits_for(StepKind.OCSR, None, "decimer-hand") == hand
    for engine in (None, Engine.DECIMER, "molnextr", Engine.FAKE):
        assert time_limits_for(StepKind.OCSR, None, engine) == TIME_LIMITS[StepKind.OCSR]
