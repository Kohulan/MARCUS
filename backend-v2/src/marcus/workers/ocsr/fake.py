"""Fake OCSR engine for fast fairness/e2e tests. Refused unless fake engines are enabled."""

import time
from pathlib import Path

from marcus.core.enums import Engine
from marcus.workers.ocsr.base import OcsrResult


class FakeEngine:
    name = Engine.FAKE
    version = "fake-1"

    def __init__(self, delay_s: float = 0.0):
        self.delay_s = delay_s

    def load(self) -> None:
        pass

    def predict(self, image: Path) -> OcsrResult:
        if self.delay_s:
            time.sleep(self.delay_s)
        return OcsrResult("c1ccccc1", None)
