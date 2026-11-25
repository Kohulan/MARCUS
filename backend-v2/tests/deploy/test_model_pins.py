"""The OCSR package pins: the images install what docker/MODEL_PINS.md names, and the stored engine
version is built from those pins (marcus.workers.ocsr.torch_common.package_commit)."""

import re
from pathlib import Path

from marcus.workers.ocsr import molparser

DOCKER = Path(__file__).resolve().parents[2] / "docker"
MOLPARSER_LIB = "f8f1e2138de92218992772b6699e7c43867f3585"


def test_the_torch_image_no_longer_installs_molnextr():
    """MolParser replaced MolNexTR (2026-11-25): neither its package nor its 1.1 GB checkpoint."""
    dockerfile = (DOCKER / "Dockerfile.torch").read_text()
    assert "MolNexTR.git@" not in dockerfile
    assert "molnextr_best.pth" not in dockerfile


def test_the_molparser_image_installs_the_pinned_library_and_model():
    dockerfile = (DOCKER / "Dockerfile.molparser").read_text()
    assert re.findall(r"dptech-corp/MolParser\.git@([0-9a-f]{40})", dockerfile) == [MOLPARSER_LIB]
    assert f"ARG MODEL_REV={molparser.MODEL_REVISION}" in dockerfile
    # every model file is fetched with its checksum, at the pinned revision
    adds = re.findall(r"ADD --checksum=sha256:[0-9a-f]{64} [^\n]*\n\s+\$\{HF\}/(\S+) ", dockerfile)
    assert "model.safetensors" in adds and len(adds) == 11
    assert "ENV" in dockerfile and "HF_HUB_OFFLINE=1" in dockerfile


def test_model_pins_names_the_same_molparser_pins_and_engine_version():
    pins = (DOCKER / "MODEL_PINS.md").read_text()
    row = next(line for line in pins.splitlines() if line.startswith("| molparser (engine"))
    assert f"`{MOLPARSER_LIB}`" in row
    assert f"version `{MOLPARSER_LIB[:7]}+{molparser.MODEL_REVISION[:7]}`" in row
    model = next(line for line in pins.splitlines() if line.startswith("| MolParser-Mobile-V2"))
    assert f"`{molparser.MODEL_REVISION}`" in model and "CC BY-NC-SA 4.0" in model
