import os

from marcus.core.enums import Engine, StepKind

_CPU_KINDS = {StepKind.CHECK_PDF, StepKind.RENDER_PAGE, StepKind.DOCLING, StepKind.DOI}
_OCSR_QUEUES = {
    Engine.DECIMER: "q.decimer",
    Engine.DECIMER_HAND: "q.decimer",
    Engine.MOLNEXTR: "q.molnextr",
    Engine.MOLSCRIBE: "q.molscribe",
    Engine.FAKE: "q.fake",
}


def queue_for(kind: StepKind, engine: Engine | None) -> str:
    if kind in _CPU_KINDS:
        return "q.cpu"
    if kind == StepKind.SEGMENT_PAGE:
        return "q.segment"
    if kind == StepKind.ANNOTATE:
        return "q.llm"
    if kind == StepKind.OCSR:
        if engine is None:
            raise ValueError("ocsr steps require an engine")
        return _OCSR_QUEUES[engine]
    raise ValueError(f"unknown step kind: {kind!r}")


_DEFAULT_SLOTS = {
    "q.cpu": 4,
    "q.segment": 1,
    "q.decimer": 1,
    "q.molnextr": 1,
    "q.molscribe": 1,
    "q.fake": 1,
    "q.llm": 1,
}


def _load_slots() -> dict[str, int]:
    slots = {}
    for queue, default in _DEFAULT_SLOTS.items():
        env = "MARCUS_SLOTS_" + queue.replace(".", "_").upper()
        slots[queue] = int(os.environ.get(env, default))
    return slots


SLOTS: dict[str, int] = _load_slots()

# Synchronous tools (depict, MCS, ...): not a pipeline queue, so no dispatcher slots.
TOOLS_QUEUE = "q.tools"

# (soft, hard) seconds
TIME_LIMITS: dict[StepKind, tuple[int, int]] = {
    StepKind.CHECK_PDF: (20, 30),
    StepKind.RENDER_PAGE: (30, 45),
    StepKind.SEGMENT_PAGE: (60, 90),
    StepKind.OCSR: (30, 45),
    StepKind.DOCLING: (300, 360),
    StepKind.DOI: (15, 20),
    StepKind.ANNOTATE: (120, 150),
}


# Docling time scales with the page count (~11 s/page measured): soft = max(300, 60 + 12 x pages).
DOCLING_MIN_SOFT_S = 300
DOCLING_FIXED_S = 60
DOCLING_PER_PAGE_S = 12
DOCLING_HARD_EXTRA_S = 60


def time_limits_for(kind: StepKind, pages: int | None) -> tuple[int, int]:
    """(soft, hard) seconds for a step. Only docling depends on the paper's page count."""
    if StepKind(kind) is StepKind.DOCLING:
        soft = max(DOCLING_MIN_SOFT_S, DOCLING_FIXED_S + DOCLING_PER_PAGE_S * (pages or 0))
        return soft, soft + DOCLING_HARD_EXTRA_S
    return TIME_LIMITS[StepKind(kind)]
