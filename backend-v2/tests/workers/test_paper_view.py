"""The tools task `paper_view` (marcus.workers.paper_view): each answer's atoms and bonds at the
paper layout's pixels, and the atoms where it differs from the other answers; and the `marks`
option of the CDK drawing (marcus.workers.tools.depict)."""

import json
import os
from pathlib import Path

import pytest
from rdkit import Chem

from marcus.core import paper_layout
from marcus.workers import paper_view as pv
from marcus.workers.ocsr import layout
from marcus.workers.tools import ToolInputError

FIXTURES = Path(__file__).parent.parent / "fixtures" / "layout"
RAW = json.loads((FIXTURES / "raw.json").read_text())
CASE = layout.layout_molfile(FIXTURES / "crop.png", RAW["atoms"], RAW["bonds"])
DECIMER = "CC[C@@H](C)C(=O)O[C@@H]1C2=C(C)C(=O)O[C@]32C=C(C)[C@@](C)(CC[C@H](C)C1=O)O3"
MOLPARSER = "CC[C@@H](C)C(=O)O[C@H]1C(=O)[C@@H](C)CC[C@H]2C=C[C@@]3(OC(=O)C(C)=C13)O2"

CDK_DIR = Path(
    os.environ.get("MARCUS_CDK_JAR_DIR", "/home/kohulan/MARCUS/judges/stack/data/cache/CDK_Jar")
)
needs_cdk = pytest.mark.skipif(
    not (CDK_DIR / "cdk-2.10.jar").exists() or not (CDK_DIR / "centres.jar").exists(),
    reason=f"CDK jars (cdk-2.10.jar, centres.jar) not found in {CDK_DIR}",
)


def _symbols(smiles: str, atoms) -> list[str]:
    mol = Chem.MolFromSmiles(smiles)
    return sorted(mol.GetAtomWithIdx(i).GetSymbol() for i in atoms)


# --- differences ----------------------------------------------------------------------------


def test_an_extra_atom_is_marked_and_so_is_where_it_is_missing():
    """Toluene against benzene: the methyl is marked in toluene; benzene lacks it, so the ring
    carbon where it would attach is marked there (an answer that lacks an atom has no atom to
    mark by itself). The same carbon is marked in toluene too."""
    marks, complete = pv.differences(["Cc1ccccc1", "c1ccccc1"])
    assert complete
    assert marks[0] == [0, 1]  # the methyl and its ring carbon
    assert len(marks[1]) == 1  # one ring carbon (any: the ring is symmetric)


def test_a_different_element_is_marked_in_both():
    marks, _ = pv.differences(["CCO", "CCN"])
    assert marks == [[1, 2], [1, 2]]  # the atom and where it attaches


def test_a_different_bond_order_marks_both_ends_in_both():
    marks, _ = pv.differences(["CC=CC", "CCCC"])
    assert marks == [[1, 2], [1, 2]]
    ring, _ = pv.differences(["C1CCCCC1", "C1=CCCCC1"])
    assert len(ring[0]) == 2 and ring[1] == [0, 1]


def test_the_same_structure_has_no_marks_and_no_search(monkeypatch):
    """Identical SMILES are one answer: nothing to compare. Stereo is not compared here (the
    trust-agreement rule owns that): two stereoisomers have no marks."""

    def no_mcs(*a, **k):
        raise AssertionError("no MCS between identical SMILES")

    monkeypatch.setattr(pv.rdFMCS, "FindMCS", no_mcs)
    assert pv.differences(["CCO", "CCO"]) == ([[], []], True)
    monkeypatch.undo()
    assert pv.differences(["C[C@H](N)O", "C[C@@H](N)O"]) == ([[], []], True)


def test_marks_are_the_union_over_the_other_answers():
    marks, _ = pv.differences(["CCO", "CCN", "CCO"])
    assert marks == [[1, 2], [1, 2], [1, 2]]
    marks, _ = pv.differences(["Cc1ccccc1", "c1ccccc1", "Clc1ccccc1"])
    assert _symbols("Cc1ccccc1", marks[0]) == ["C", "C"]
    assert _symbols("Clc1ccccc1", marks[2]) == ["C", "Cl"]


def test_an_unreadable_answer_has_no_marks_and_marks_nothing():
    marks, complete = pv.differences(["CCO", "[R1]c1ccccc1", "CCN"])
    assert marks == [[1, 2], None, [1, 2]] and complete


def test_the_case_differs_at_the_two_methyls():
    """DECIMER reads two methyls MolParser does not: marked in DECIMER with their carbons;
    in MolParser the two carbons where they are missing."""
    marks, complete = pv.differences([DECIMER, MOLPARSER])
    assert complete
    assert _symbols(DECIMER, marks[0]) == ["C"] * 4
    assert _symbols(MOLPARSER, marks[1]) == ["C"] * 2
    methyls = [
        i for i in marks[0] if Chem.MolFromSmiles(DECIMER).GetAtomWithIdx(i).GetDegree() == 1
    ]
    assert len(methyls) == 2


# --- one shared time budget -----------------------------------------------------------------


def test_every_search_draws_on_one_budget(monkeypatch):
    """Four answers: up to four layout searches and six pairs, all inside VIEW_BUDGET_S (the
    task's soft limit is 5 s). A search starts only with a whole second left; what was skipped
    is said (`complete` false)."""
    clock = [0.0]
    seen = []
    real = pv.rdFMCS.FindMCS

    def slow(mols, **kwargs):
        seen.append(kwargs["timeout"])
        clock[0] += 1.0  # every search takes its whole second
        return real(mols, **kwargs)

    monkeypatch.setattr(pv.rdFMCS, "FindMCS", slow)
    monkeypatch.setattr(pv.orient.rdFMCS, "FindMCS", slow)
    monkeypatch.setattr(pv.time, "monotonic", lambda: clock[0])
    out = pv.paper_view(["CCO", "CCN", "CCS", "CCCl"], CASE)
    assert len(seen) == pv.VIEW_BUDGET_S and all(1 <= t <= pv.VIEW_BUDGET_S for t in seen)
    assert seen == sorted(seen, reverse=True)  # each gets what is left
    assert out["complete"] is False
    assert pv.VIEW_BUDGET_S <= 4


def test_a_search_that_ran_out_of_time_gives_no_marks(monkeypatch):
    real = pv.rdFMCS.FindMCS

    class Canceled:
        def __init__(self, result):
            self.canceled = True
            self.smartsString, self.numAtoms = result.smartsString, result.numAtoms

    monkeypatch.setattr(pv.rdFMCS, "FindMCS", lambda mols, **k: Canceled(real(mols, **k)))
    assert pv.differences(["CCO", "CCN"]) == ([[], []], False)


# --- the view -------------------------------------------------------------------------------


def test_the_case_on_the_paper():
    out = pv.paper_view([DECIMER, MOLPARSER], CASE)
    info = paper_layout.info(CASE)
    assert (out["fit"], out["bond"], out["width"], out["height"]) == (
        info.fit, info.bond, 585, 689,
    )  # fmt: skip
    assert out["overlay"] is True and out["complete"] is True
    decimer, molparser = out["answers"]
    assert len(decimer["atoms"]) == 27 and len(molparser["atoms"]) == 25
    for answer, smiles in ((decimer, DECIMER), (molparser, MOLPARSER)):
        mol = Chem.MolFromSmiles(smiles)
        assert [a[2] for a in answer["atoms"]] == [a.GetSymbol() for a in mol.GetAtoms()]
        assert len(answer["bonds"]) == mol.GetNumBonds()
        assert {b[2] for b in answer["bonds"]} <= {1, 1.5, 2, 3}
        placed = [a for a in answer["atoms"] if a[3]]
        assert len(placed) >= len(answer["atoms"]) - 2
        # placed atoms are in the crop's pixels (y down), on the drawing
        assert all(0 <= x <= 585 and 0 <= y <= 689 for x, y, _, _ in placed)
    assert decimer["marks"] and molparser["marks"]
    # the SMILES's first atom (the ethyl end of the ester side chain) is at the bottom right
    # of the paper's drawing in both answers
    for answer in (decimer, molparser):
        x, y = answer["atoms"][0][:2]
        assert x > 585 / 2 and y > 689 / 2
    assert json.loads(json.dumps(out)) == out  # plain JSON for the result backend


def test_a_poor_fit_is_said_and_the_geometry_still_comes():
    mirrored = layout.layout_molfile(
        FIXTURES / "crop.png", [{**a, "x": 1 - a["x"]} for a in RAW["atoms"]], RAW["bonds"]
    )
    out = pv.paper_view([DECIMER], mirrored)
    assert out["overlay"] is False and out["fit"] > 0.04 * out["bond"]


def test_one_answer_has_geometry_and_no_marks():
    out = pv.paper_view([MOLPARSER], CASE)
    assert out["answers"][0]["marks"] == [] and len(out["answers"][0]["atoms"]) == 25


def test_an_answer_that_cannot_be_placed_keeps_its_marks():
    """Too little in common with the drawing: no geometry (never a made-up place), marks stay.
    An answer RDKit cannot read: null."""
    out = pv.paper_view(["N#N", "NN", "[R1]C"], CASE)
    assert out["answers"][0] == {"marks": [0, 1], "atoms": None, "bonds": None}
    assert out["answers"][2] is None


@pytest.mark.parametrize(
    ("smiles", "template"),
    [
        ([], CASE),
        (["C"] * (pv.MAX_ANSWERS + 1), CASE),
        (["CCO"], "not a layout"),
        (["CCO"], "\n" + CASE.split("\n", 1)[1]),  # a molfile without the layout's title
        (["CCO"], ""),
        ("CCO", CASE),
        ([5], CASE),
    ],
)
def test_bad_input_is_refused(smiles, template):
    with pytest.raises(ToolInputError):
        pv.paper_view(smiles, template)


def test_paper_view_is_a_tools_task_with_the_tools_limits():
    from marcus.workers import tools

    task = tools.paper_view_task
    assert task.name == "marcus.tools.paper_view"
    assert (task.soft_time_limit, task.time_limit) == (5, 10)
    assert tools.paper_view_task.run(["CCO"], "x") == {
        "ok": False,
        "error": "not a paper layout",
    }
    assert tools.paper_view_task.run([MOLPARSER], CASE)["ok"] is True


# --- marks in the CDK drawing ---------------------------------------------------------------

ORANGE = "#fa3600"


@pytest.fixture
def _jar_dir(monkeypatch):
    monkeypatch.setenv("MARCUS_CDK_JAR_DIR", str(CDK_DIR))


@needs_cdk
def test_marked_atoms_get_an_orange_glow(_jar_dir):
    from marcus.workers.tools import depict

    plain = depict("Cc1ccccc1", "svg", 300, 300)
    marked = depict("Cc1ccccc1", "svg", 300, 300, marks=[0, 1])
    assert ORANGE not in plain.lower()
    assert marked != plain and ORANGE in marked.lower()
    assert depict("Cc1ccccc1", "svg", 300, 300, marks=[]) == plain
    assert depict("Cc1ccccc1", "svg", 300, 300, marks=None) == plain


@needs_cdk
def test_marks_and_the_common_part_show_together(_jar_dir):
    from marcus.workers.tools import depict

    both = depict("Cc1ccccc1", "svg", 300, 300, highlight="c1ccccc1", marks=[0]).lower()
    assert ORANGE in both and "#add8e6" in both


@needs_cdk
@pytest.mark.parametrize("marks", [[7], [-1], [0, 0], ["0"], [True], list(range(300)), "01"])
def test_marks_that_do_not_fit_the_molecule_are_refused(_jar_dir, marks):
    from marcus.workers.tools import depict

    with pytest.raises(ToolInputError):
        depict("Cc1ccccc1", "svg", 300, 300, marks=marks)


@needs_cdk
def test_the_depict_task_takes_marks(_jar_dir):
    from marcus.workers import tools

    out = tools.depict_task.run("CCO", "svg", 200, 200, "", "", [2])
    assert out["ok"] and ORANGE in out["result"].lower()
    assert tools.depict_task.run("CCO", "svg", 200, 200, marks=[9])["ok"] is False
