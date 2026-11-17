"""Helpers shared by the torch OCSR engines (MolNexTR, MolScribe). Nothing here imports torch or
the model packages at import time.

- `package_commit`: the engine version is the git commit the package was installed from
  (PEP 610 direct_url.json, written by the installer), short form.
- `serial_graph_conversion`: both libraries turn the decoded graph into SMILES and a molfile
  with `convert_graph_to_smiles(..., num_workers=16)`, which opens a `multiprocessing.Pool` of
  16 processes on every prediction. In a Celery prefork pool process that would fork the whole
  model process 16 times per structure. The engines run the same per-structure function
  (`_convert_graph_to_smiles`) in-process instead, in the same order. (A pool cannot even start
  there: "daemonic processes are not allowed to have children". MolNexTR's own
  `num_workers <= 1` branch would do the same as this function but fails with a NameError.)
  In-process, the conversion now runs inside the step's time limit, so a soft time limit can
  interrupt it like any other part of the prediction (theoretical: it takes milliseconds per
  structure).
- `warm_up`: one prediction on a small RDKit drawing when the model loads.
"""

import itertools
import json
import logging
import tempfile
import time
from collections.abc import Callable
from importlib.metadata import distribution

log = logging.getLogger(__name__)


def package_commit(dist_name: str, length: int = 7) -> str:
    """Short hash of the commit `dist_name` was installed from (git URL install)."""
    text = distribution(dist_name).read_text("direct_url.json")
    commit = (json.loads(text or "{}").get("vcs_info") or {}).get("commit_id")
    if not commit:
        raise RuntimeError(f"{dist_name} was not installed from a pinned git commit")
    return commit[:length]


def serial_graph_conversion(convert_one: Callable) -> Callable:
    """`convert_graph_to_smiles(coords, symbols, edges, images=None, num_workers=16)` without the
    process pool: `convert_one` is the library's per-structure `_convert_graph_to_smiles`."""

    def convert_graph_to_smiles(coords, symbols, edges, images=None, num_workers=16):
        import numpy as np

        if images is None:
            args = zip(coords, symbols, edges)
        else:
            args = zip(coords, symbols, edges, images)
        results = list(itertools.starmap(convert_one, args))
        smiles_list, molblock_list, success = zip(*results)
        return smiles_list, molblock_list, np.mean(success)

    return convert_graph_to_smiles


WARM_UP_SMILES = "CC(=O)Oc1ccccc1C(=O)O"  # aspirin


def warm_up(name: str, predict: Callable[[str], str]) -> None:
    """One prediction on an RDKit drawing of aspirin, so the first ocsr step does not pay the
    model's first-call cost. `predict(path)` returns the SMILES (logged)."""
    from rdkit import Chem
    from rdkit.Chem.Draw import rdMolDraw2D

    drawer = rdMolDraw2D.MolDraw2DCairo(300, 300)
    drawer.DrawMolecule(Chem.MolFromSmiles(WARM_UP_SMILES))
    drawer.FinishDrawing()
    start = time.monotonic()
    with tempfile.NamedTemporaryFile(suffix=".png") as f:
        f.write(drawer.GetDrawingText())
        f.flush()
        smiles = predict(f.name)
    log.info("%s warm-up in %.1f s (%s)", name, time.monotonic() - start, smiles)
