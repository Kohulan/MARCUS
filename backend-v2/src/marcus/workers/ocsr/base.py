"""OCSR engine protocol and the per-process engine registry.

Real engines register a factory with `register_engine` (Phase B); nothing here imports them.
"""

import logging
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from marcus.core.enums import Engine
from marcus.core.settings import get_settings

log = logging.getLogger(__name__)


@dataclass
class OcsrResult:
    smiles: str
    molfile: str | None = None


class OcsrEngine(Protocol):
    name: Engine
    version: str

    def load(self) -> None: ...

    def predict(self, image: Path) -> OcsrResult: ...


FACTORIES: dict[str, Callable[[], OcsrEngine]] = {}
_ENGINES: dict[str, OcsrEngine] = {}
_lock = threading.Lock()


def register_engine(name: Engine | str, factory: Callable[[], OcsrEngine]) -> None:
    FACTORIES[str(Engine(name))] = factory


def _fake_factory() -> OcsrEngine:
    from marcus.workers.ocsr.fake import FakeEngine

    return FakeEngine(delay_s=float(os.environ.get("MARCUS_FAKE_OCSR_DELAY_S", "0")))


FACTORIES["fake"] = _fake_factory


def get_engine(name: Engine | str) -> OcsrEngine:
    """One instance per process, created and `load()`ed on first use."""
    key = str(Engine(name))
    if key == Engine.FAKE and not get_settings().enable_fake_engines:
        raise RuntimeError("fake engine is disabled (MARCUS_ENABLE_FAKE_ENGINES is not set)")
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
