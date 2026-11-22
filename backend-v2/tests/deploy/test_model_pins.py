"""The OCSR package pins: the torch image installs the commit docker/MODEL_PINS.md names, and the
stored engine version is its short hash (marcus.workers.ocsr.torch_common.package_commit)."""

import re
from pathlib import Path

DOCKER = Path(__file__).resolve().parents[2] / "docker"
# MolNexTR with the image's atom positions kept in its molfile (Kohulan/MolNexTR PR #1); the
# SMILES are those of fb7505b, the v1 commit.
MOLNEXTR = "7a4e03f22c13f4c1c236effa9dab4a365a8e08d5"


def test_the_torch_image_installs_the_molnextr_that_keeps_the_image_positions():
    dockerfile = (DOCKER / "Dockerfile.torch").read_text()
    assert re.findall(r"Kohulan/MolNexTR\.git@([0-9a-f]{40})", dockerfile) == [MOLNEXTR]


def test_model_pins_names_the_same_molnextr_commit_and_engine_version():
    pins = (DOCKER / "MODEL_PINS.md").read_text()
    row = next(line for line in pins.splitlines() if line.startswith("| MolNexTR (engine"))
    assert f"`{MOLNEXTR}`" in row
    assert f"version `{MOLNEXTR[:7]}`" in row
