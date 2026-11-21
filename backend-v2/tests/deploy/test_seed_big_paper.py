"""The big-paper e2e seed (tests/e2e/seed_big_paper.py) refuses any stack without the fake
engines, so it never writes rows or deletes depictions outside the local e2e stack."""

import os
import subprocess
import sys
from pathlib import Path

SEED = Path(__file__).resolve().parents[1] / "e2e" / "seed_big_paper.py"


def test_seed_refuses_without_fake_engines():
    env = {k: v for k, v in os.environ.items() if not k.startswith("MARCUS_")}
    # Unreachable, so a seed without the guard fails instead of writing anywhere.
    env["MARCUS_DATABASE_URL"] = "postgresql+asyncpg://x:x@127.0.0.1:9/x"
    out = subprocess.run(
        [sys.executable, "-"],
        input=SEED.read_text(),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert out.returncode == 2, out.stderr
    assert "refusing" in out.stderr
    assert out.stdout == ""
