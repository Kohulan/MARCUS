"""OCSR package: importing it registers the `ocsr` handler and the engines this worker serves.

`MARCUS_OCSR_ENGINES` (comma list) names the engines of this worker process; each one's module
is imported here and registers its factory. Engine modules never import their ML stack at
import time: models load in the pool process (base.preload_engines) or on first request.
"""

import importlib

from marcus.core.enums import Engine
from marcus.workers.ocsr import handler  # noqa: F401
from marcus.workers.ocsr.base import configured_engines

# Engine -> module with `register(name)`. The fake engine is always registered (base.py) and
# refused unless fake engines are enabled.
ENGINE_MODULES: dict[Engine, str] = {
    Engine.DECIMER: "marcus.workers.ocsr.decimer",
    Engine.DECIMER_HAND: "marcus.workers.ocsr.decimer",
    Engine.MOLPARSER: "marcus.workers.ocsr.molparser",
    Engine.MOLSCRIBE: "marcus.workers.ocsr.molscribe",
}


def register_configured_engines() -> list[Engine]:
    """Register every engine named in MARCUS_OCSR_ENGINES. Unknown or unbuilt engines stop the
    worker at start (a config error), never at the first step."""
    names = configured_engines()
    for name in names:
        if name is Engine.FAKE:
            continue
        module = ENGINE_MODULES.get(name)
        if module is None:
            raise RuntimeError(f"OCSR engine {name.value!r} is not available in this build")
        importlib.import_module(module).register(name)
    return names


register_configured_engines()
