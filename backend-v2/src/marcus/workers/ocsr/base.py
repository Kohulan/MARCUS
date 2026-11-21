"""OCSR engine protocol, the per-process engine registry and the model preload hook.

Real engines register a factory with `register_engine`; nothing here imports them (the
package `marcus.workers.ocsr` imports the engine modules listed in `MARCUS_OCSR_ENGINES`).
When a pool process starts, `preload_engines` loads every configured engine registered with
`preload=True`; the others (decimer-hand) load on their first request.
"""

import logging
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from celery.signals import worker_process_init

from marcus.core.enums import Engine
from marcus.core.settings import fake_enabled
from marcus.workers.runtime import preload_on_worker_init

log = logging.getLogger(__name__)


@dataclass
class OcsrResult:
    smiles: str
    molfile: str | None = None


class OcsrEngine(Protocol):
    """`version` is static (package version or pinned commit) and set by the constructor:
    constructing an engine is cheap and never loads a model (that is `load()`), so the OCSR
    cache can be checked before any model is loaded (`engine_version`)."""

    name: Engine
    version: str

    def load(self) -> None:
        """Load the model (never at construction)."""

    def predict(self, image: Path) -> OcsrResult:
        """The structure drawn in the image."""


ENGINES_ENV = "MARCUS_OCSR_ENGINES"

FACTORIES: dict[str, Callable[[], OcsrEngine]] = {}
PRELOAD: set[str] = set()  # engines loaded when a pool process starts
_ENGINES: dict[str, OcsrEngine] = {}
_VERSIONS: dict[str, tuple[Callable[[], OcsrEngine], str]] = {}  # key -> (factory, version)
_lock = threading.Lock()


def register_engine(
    name: Engine | str, factory: Callable[[], OcsrEngine], *, preload: bool = True
) -> None:
    """Make `name` available in this process. `preload=False`: load on first request only."""
    key = str(Engine(name))
    FACTORIES[key] = factory
    if preload:
        PRELOAD.add(key)
    else:
        PRELOAD.discard(key)


def configured_engines() -> list[Engine]:
    """Engines this worker serves: env MARCUS_OCSR_ENGINES, a comma list (empty = none)."""
    raw = os.environ.get(ENGINES_ENV, "")
    names = [part.strip() for part in raw.split(",") if part.strip()]
    try:
        return list(dict.fromkeys(Engine(name) for name in names))
    except ValueError as exc:
        raise RuntimeError(f"{ENGINES_ENV}: unknown engine in {raw!r}") from exc


def _fake_factory() -> OcsrEngine:
    from marcus.workers.ocsr.fake import FakeEngine

    return FakeEngine(delay_s=float(os.environ.get("MARCUS_FAKE_OCSR_DELAY_S", "0")))


FACTORIES["fake"] = _fake_factory


def _checked_key(name: Engine | str) -> str:
    key = str(Engine(name))
    if key == Engine.FAKE and not fake_enabled():
        raise RuntimeError("fake engine is disabled (MARCUS_ENABLE_FAKE_ENGINES is not set)")
    return key


def engine_version(name: Engine | str) -> str:
    """The engine's version without loading its model (the OCSR cache key needs only this; a
    cache hit on a lazily loaded engine such as decimer-hand must not pay its model load).

    A loaded engine answers itself; otherwise an unloaded instance is constructed (cheap, see
    OcsrEngine) and its version is kept per process, tied to the registered factory."""
    key = _checked_key(name)
    with _lock:
        engine = _ENGINES.get(key)
        if engine is not None:
            return engine.version
        factory = FACTORIES.get(key)
        if factory is None:
            raise RuntimeError(f"OCSR engine {key!r} is not available in this worker")
        cached = _VERSIONS.get(key)
        if cached is not None and cached[0] is factory:
            return cached[1]
        version = factory().version
        _VERSIONS[key] = (factory, version)
        return version


def get_engine(name: Engine | str) -> OcsrEngine:
    """One instance per process, created and `load()`ed on first use."""
    key = _checked_key(name)
    with _lock:
        engine = _ENGINES.get(key)
        if engine is None:
            factory = FACTORIES.get(key)
            if factory is None:
                raise RuntimeError(f"OCSR engine {key!r} is not available in this worker")
            engine = factory()
            engine.load()
            _ENGINES[key] = engine
            log.info("loaded OCSR engine %s %s", key, engine.version)
        return engine


@worker_process_init.connect
def preload_engines(**_) -> None:
    """Load the configured preload engines when a pool process starts (after the fork), so the
    first ocsr step does not pay the model load against its time limit.

    A failed load stops the whole worker with a non-zero exit (runtime.abort_worker): compose
    restarts it and /ready reports the queue as unserved. Only in a Celery pool process.
    """
    preload_on_worker_init(_load_preload_engines, "OCSR engines")


def _load_preload_engines() -> None:
    for name in configured_engines():
        if name in PRELOAD:
            log.info("preloaded OCSR engine %s %s", name, get_engine(name).version)
