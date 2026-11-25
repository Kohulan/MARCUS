"""MolParser OCSR engine `molparser` (torch, q.molparser worker; owner decision 2026-11-25: it
replaces MolNexTR).

Model: MolParser-Mobile-V2 (Hugging Face UniParser/MolParser-Mobile-V2, weights CC BY-NC-SA 4.0),
called through the MolParser library (dptech-corp/MolParser, Apache-2.0) the way its
`MolParser.parse(path, rec_only=True)` does for one crop: `MolParserRecognizer.recognize` (greedy
decoding, max_length 256, fp16 on CUDA, fp32 on CPU) and then `utils.postprocess_caption`, whose
`smi` is the SMILES. No MolDet detection (MARCUS segments the page itself) and no padding
(the library's default `padding_px` 0). MARCUS-training review-feedback/molparser-eval: on the
140 phase-B crops this gives 64/119 right against MolNexTR's 58/119, and the same SMILES on
all 140 crops as the library's own `parse` (pinned stack, CPU).

Output is E-SMILES: R groups and abbreviations it could not expand are bare `*` atoms in `smi`,
their labels in the extension (`<a>0:R[1]</a>`). MolParser reads no atom positions, so there is
no image molfile. Only when a `*` atom has a label is a molfile written: RDKit's, from the
CXSMILES (`|$R[1];;...$|`), with the label as the atom's alias (R[1] -> R1) and a computed 2D
layout, so the R-group labels reach marcus.core.rgroups as they do from the other engines. A
computed layout is never a template (molparser is not a template engine: api/depiction.py).

The model files are baked into the image at MODEL_DIR (pinned revision, sha256 at build time);
the model code is the repository's own remote code, loaded from there (trust_remote_code) with
the hub offline. Before the import: torch thread caps and the GPU memory share
(marcus.workers.gpu.prepare_torch). The model loads and warms up when the pool process starts
(base.preload_engines). This module does not import torch or molparser at import time.
"""

import logging
import os
import re
import time
from pathlib import Path

from marcus.core.enums import Engine
from marcus.workers.ocsr.base import OcsrResult, register_engine
from marcus.workers.ocsr.torch_common import package_commit, warm_up

log = logging.getLogger(__name__)

DIST_NAME = "molparser"
MODEL_REVISION = "6ee7c0f7e03cde6e5f871f7a764ad4462bb59797"  # UniParser/MolParser-Mobile-V2
MODEL_DIR_ENV = "MARCUS_MOLPARSER_MODEL_DIR"
DEFAULT_MODEL_DIR = "/opt/models/molparser-mobile-v2"
MAX_LENGTH = 256  # the library's default (molparser/models/config.yaml)

_R_LABEL = re.compile(r"^R\[([^\]]+)\]$")  # E-SMILES R[1] / R[1'] -> R1 / R1'


def model_dir() -> Path:
    return Path(os.environ.get(MODEL_DIR_ENV, DEFAULT_MODEL_DIR))


def alias_of(label: str) -> str:
    """The molfile alias of an E-SMILES atom label: R[n] -> Rn, any other label as it is."""
    match = _R_LABEL.match(label)
    return f"R{match.group(1)}" if match else label


def labelled_molfile(cxsmiles: str) -> str | None:
    """A molfile with each labelled `*` atom's label as its alias and a computed 2D layout, or
    None when no `*` atom has a label or RDKit cannot read the CXSMILES."""
    if not cxsmiles or "$" not in cxsmiles:
        return None
    from rdkit import Chem
    from rdkit.Chem import AllChem
    from rdkit.rdBase import BlockLogs

    with BlockLogs():
        mol = Chem.MolFromSmiles(cxsmiles)
        if mol is None:
            return None
        labelled = False
        for atom in mol.GetAtoms():
            if atom.GetAtomicNum() == 0 and atom.HasProp("atomLabel"):
                label = atom.GetProp("atomLabel").strip()
                if label:
                    atom.SetProp("molFileAlias", alias_of(label))
                    labelled = True
        if not labelled:
            return None
        AllChem.Compute2DCoords(mol)
        return Chem.MolToMolBlock(mol)


def result_of(caption: str) -> OcsrResult:
    """The OcsrResult of one raw model caption (E-SMILES)."""
    from molparser.utils import postprocess_caption

    out = postprocess_caption(caption)
    smiles = out.get("smi") or ""
    return OcsrResult(smiles, labelled_molfile(out.get("cxsmiles") or ""))


class MolparserEngine:
    name = Engine.MOLPARSER

    def __init__(self) -> None:
        self.version = f"{package_commit(DIST_NAME)}+{MODEL_REVISION[:7]}"
        self.device = None
        self._model = None

    def load(self) -> None:
        if self._model is not None:
            return
        from marcus.workers import gpu

        gpu.prepare_torch()
        path = model_dir()
        if not (path / "model.safetensors").is_file():
            raise RuntimeError(f"MolParser model missing at {path} (baked into the image)")
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

        start = time.monotonic()
        import torch
        from molparser.models.runtime import MolParserRecognizer

        device = "cuda" if torch.cuda.is_available() else "cpu"
        self._model = MolParserRecognizer(str(path), device=device, max_length=MAX_LENGTH)
        self.device = self._model.device
        if self.device.type != "cuda" and torch.cuda.is_available():
            raise RuntimeError("MolParser model is not on the GPU although CUDA is visible")
        log.info("MolParser loaded on %s in %.1f s", self.device, time.monotonic() - start)
        warm_up("MolParser", lambda p: self.predict(Path(p)).smiles)

    def predict(self, image: Path) -> OcsrResult:
        if self._model is None:
            raise RuntimeError("MolparserEngine.predict() called before load()")
        from PIL import Image

        with Image.open(image) as img:
            caption = self._model.recognize([img.convert("RGB")])[0]
        return result_of(caption)


def register(name: Engine) -> None:
    """Called by marcus.workers.ocsr when `molparser` is configured."""
    if Engine(name) is not Engine.MOLPARSER:
        raise ValueError(f"not the MolParser engine: {name!r}")
    register_engine(Engine.MOLPARSER, MolparserEngine)
