"""Pluggable filesystem probe for the security judge.

Some tests need to know the truth on disk (did a path-traversal write land
outside the upload folder?) that the HTTP API alone can't show. They get it
through a small probe interface instead of hard-coding `docker exec`, so the
MARCUS v2 rebuild can point the same tests at its own filesystem (a
different container, a k8s pod, a local path) by setting MARCUS_FS_PROBE and
without touching this file or the tests.

Selected with the env var MARCUS_FS_PROBE, e.g.:

    MARCUS_FS_PROBE=docker:marcus-judge-backend

Per the judges' design rule, a test that needs a probe and doesn't have one
must ERROR, never silently skip. get_probe() raises ProbeError for that.
"""
from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass


class ProbeError(RuntimeError):
    """Raised when no usable filesystem probe is configured or reachable."""


class FsProbe:
    """Interface every probe backend implements."""

    def exists(self, path: str) -> bool:  # pragma: no cover - interface
        raise NotImplementedError

    def read_bytes(self, path: str) -> bytes:  # pragma: no cover - interface
        raise NotImplementedError

    def write_bytes(self, path: str, data: bytes) -> None:  # pragma: no cover
        raise NotImplementedError

    def remove(self, path: str) -> None:  # pragma: no cover - interface
        raise NotImplementedError


@dataclass
class DockerProbe(FsProbe):
    """Probe backend that shells out to `docker exec` on a named container."""

    container: str

    def exists(self, path: str) -> bool:
        r = subprocess.run(
            ["docker", "exec", self.container, "test", "-e", path],
            capture_output=True,
        )
        return r.returncode == 0

    def read_bytes(self, path: str) -> bytes:
        r = subprocess.run(
            ["docker", "exec", self.container, "cat", path],
            capture_output=True,
        )
        if r.returncode != 0:
            raise ProbeError(
                f"could not read {path!r} in container {self.container!r}: "
                f"{r.stderr.decode(errors='replace').strip()}"
            )
        return r.stdout

    def write_bytes(self, path: str, data: bytes) -> None:
        r = subprocess.run(
            [
                "docker", "exec", "-i", self.container,
                "sh", "-c", f"cat > {shlex.quote(path)}",
            ],
            input=data,
            capture_output=True,
        )
        if r.returncode != 0:
            raise ProbeError(
                f"could not write {path!r} in container {self.container!r}: "
                f"{r.stderr.decode(errors='replace').strip()}"
            )

    def remove(self, path: str) -> None:
        subprocess.run(
            ["docker", "exec", self.container, "rm", "-f", path],
            capture_output=True,
        )


def get_probe() -> FsProbe:
    """Return the configured filesystem probe.

    Raises ProbeError (not a skip) when MARCUS_FS_PROBE is unset or its
    backend is unreachable, so a test that depends on it errors loudly
    instead of silently passing.
    """
    spec = os.environ.get("MARCUS_FS_PROBE")
    if not spec:
        raise ProbeError(
            "MARCUS_FS_PROBE is not set. Set e.g. "
            "MARCUS_FS_PROBE=docker:marcus-judge-backend so filesystem-probe "
            "tests have something to check evidence against."
        )

    kind, _, target = spec.partition(":")

    if kind == "docker":
        if not target:
            raise ProbeError(
                "MARCUS_FS_PROBE=docker:<container> needs a container name"
            )
        check = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", target],
            capture_output=True,
            text=True,
        )
        if check.returncode != 0 or check.stdout.strip() != "true":
            raise ProbeError(
                f"MARCUS_FS_PROBE container {target!r} is not running "
                f"(docker inspect: {check.stderr.strip() or check.stdout.strip()})"
            )
        return DockerProbe(target)

    raise ProbeError(f"Unknown MARCUS_FS_PROBE backend {kind!r}")
