"""The API sends an engine molfile with wedge bonds with chiral flag 1 (absolute stereo)."""

import uuid
from datetime import UTC, datetime

from rdkit import Chem

from marcus.api.schemas import ImagePrediction, PredictionOut

RDKIT_MOLFILE = Chem.MolToMolBlock(Chem.MolFromSmiles("C[C@H](N)C(=O)O"))  # flag 0


def _flag(molfile: str) -> str:
    return molfile.splitlines()[3][12:15]


def test_prediction_out_sets_the_chiral_flag():
    out = PredictionOut.model_validate(
        {
            "id": uuid.uuid4(),
            "engine": "molnextr",
            "engine_version": "m",
            "smiles": "C[C@H](N)C(=O)O",
            "molfile": RDKIT_MOLFILE,
            "valid": True,
            "ms": 1,
            "cached": False,
            "created_at": datetime.now(UTC),
        }
    )
    assert _flag(out.molfile) == "  1"


def test_image_prediction_sets_the_chiral_flag():
    out = ImagePrediction.model_validate(
        {
            "smiles": "C[C@H](N)C(=O)O",
            "molfile": RDKIT_MOLFILE,
            "valid": True,
            "engine": "molscribe",
            "engine_version": "s",
            "ms": 1,
        }
    )
    assert _flag(out.molfile) == "  1"


def test_no_molfile_stays_none():
    out = ImagePrediction.model_validate(
        {
            "smiles": "C",
            "molfile": None,
            "valid": True,
            "engine": "decimer",
            "engine_version": "d",
            "ms": 1,
        }
    )
    assert out.molfile is None
