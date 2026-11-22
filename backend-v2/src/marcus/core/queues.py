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
    if kind == StepKind.RGROUPS:
        # its own queue: the R-group model has its own llama-server (llama-rgroup), so an
        # annotation run never holds back an R-group reading, nor the other way round
        return "q.rgroup"
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
    "q.rgroup": 1,
}


def _per_queue_env(prefix: str, defaults: dict[str, int]) -> dict[str, int]:
    """Per-queue ints, each overridable by env `<prefix><QUEUE>` (q.cpu -> Q_CPU)."""
    return {
        queue: int(os.environ.get(prefix + queue.replace(".", "_").upper(), default))
        for queue, default in defaults.items()
    }


SLOTS: dict[str, int] = _per_queue_env("MARCUS_SLOTS_", _DEFAULT_SLOTS)

# q.cpu slots docling may never take: docling runs for minutes per paper, so without a reserve
# four papers in docling would make a new upload's check_pdf (and render_page, doi) wait for one
# of them to end. Env override MARCUS_CPU_SLOTS_KEPT_FROM_DOCLING.
CPU_SLOTS_KEPT_FROM_DOCLING = int(os.environ.get("MARCUS_CPU_SLOTS_KEPT_FROM_DOCLING", 2))


def docling_slots() -> int:
    """How many docling steps may be queued or running at once (at least one)."""
    return max(1, SLOTS["q.cpu"] - CPU_SLOTS_KEPT_FROM_DOCLING)


# How long a step may sit `queued` (sent, not yet started) before the watchdog counts its
# delivery as lost, in seconds; independent of the step's run limit. The Celery message expires
# after the same time. On a queue with no live consumer the watchdog instead puts the step back
# to pending without counting an attempt (marcus.dispatcher.pick.watchdog_once). Model queues cover a worker
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
    "q.rgroup": _MODEL_QUEUE_WAIT_S,
}


QUEUE_WAIT_S: dict[str, int] = _per_queue_env("MARCUS_QUEUE_WAIT_S_", _DEFAULT_QUEUE_WAIT_S)

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
    # one scaffold: ~3 s measured on a V100 (README), 2,048 output tokens at ~100 tokens/s at most
    StepKind.RGROUPS: (120, 150),
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
