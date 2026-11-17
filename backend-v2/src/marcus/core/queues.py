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

# How long a step may sit `queued` (sent, not yet started) before the watchdog counts its
# delivery as lost, in seconds; independent of the step's run limit. Model queues cover a worker
# (re)start: the pool process preloads its model before it takes a step (DECIMER ~85-105 s on
# CPU), and a hard-killed or recycled process is replaced the same way. Env override:
# MARCUS_QUEUE_WAIT_S_<QUEUE>, e.g. MARCUS_QUEUE_WAIT_S_Q_DECIMER=600.
_MODEL_QUEUE_WAIT_S = 300
_DEFAULT_QUEUE_WAIT_S = {
    "q.cpu": 120,
    "q.segment": _MODEL_QUEUE_WAIT_S,
    "q.decimer": _MODEL_QUEUE_WAIT_S,
    "q.molnextr": _MODEL_QUEUE_WAIT_S,
    "q.molscribe": _MODEL_QUEUE_WAIT_S,
    "q.fake": 120,
    "q.llm": _MODEL_QUEUE_WAIT_S,
}


def _load_queue_wait() -> dict[str, int]:
    waits = {}
    for queue, default in _DEFAULT_QUEUE_WAIT_S.items():
        env = "MARCUS_QUEUE_WAIT_S_" + queue.replace(".", "_").upper()
        waits[queue] = int(os.environ.get(env, default))
    return waits


QUEUE_WAIT_S: dict[str, int] = _load_queue_wait()

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

# Per (kind, engine) overrides of TIME_LIMITS. decimer-hand loads its model on its first request
# (spec: lazy), measured on CPU with 4 TF threads: load 76 s, then graph warm-up plus prediction
# up to 23 s, ~100 s in all when quiet; steady predictions take 3-12 s. 180 s leaves room for a
# busy host. Every decimer-hand step gets it (the dispatcher cannot know whether the model is
# loaded); the normal decimer model loads at worker start and keeps the ocsr limit.
ENGINE_TIME_LIMITS: dict[tuple[StepKind, Engine], tuple[int, int]] = {
    (StepKind.OCSR, Engine.DECIMER_HAND): (180, 210),
}

# Docling time scales with the page count (~11 s/page measured): soft = max(300, 60 + 12 x pages).
DOCLING_MIN_SOFT_S = 300
DOCLING_FIXED_S = 60
DOCLING_PER_PAGE_S = 12
DOCLING_HARD_EXTRA_S = 60


def time_limits_for(
    kind: StepKind, pages: int | None, engine: Engine | str | None = None
) -> tuple[int, int]:
    """(soft, hard) seconds for a step. Docling depends on the paper's page count; an ocsr step
    may have an engine override (ENGINE_TIME_LIMITS)."""
    kind = StepKind(kind)
    if kind is StepKind.DOCLING:
        soft = max(DOCLING_MIN_SOFT_S, DOCLING_FIXED_S + DOCLING_PER_PAGE_S * (pages or 0))
        return soft, soft + DOCLING_HARD_EXTRA_S
    if engine is not None:
        for (k, e), limits in ENGINE_TIME_LIMITS.items():
            if k is kind and e.value == str(engine):
                return limits
    return TIME_LIMITS[kind]
