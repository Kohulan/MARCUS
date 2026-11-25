"""Measure Markush Phase 3 building (marcus.core.enumeration) against hand-made gold.

    cd backend-v2
    .venv/bin/python ops/measure_enumeration.py --gold GOLD.json [GOLD.json ...] [--coverage DIR]

Gold (one file per paper; written by hand from the paper, never by this code):
    {"paper": str, "scaffolds": [{"name": str, "smiles": str | null, "molfile": str | null,
      "rows": [{"compound": str, "groups": {label: value}}], "expected": {compound: full SMILES}}]}

Per compound: right (same full InChIKey as the hand-written structure), WRONG (built, other
InChIKey: both printed), could not build (the reason), or built but not in the gold (unexpected:
counted as wrong, a row the gold says must not build). `--coverage DIR`: the share of the Phase 2
gold values (markush-testset gold/*.json) the resolver accepts. Exit 1 when anything is wrong.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rdkit import Chem

from marcus.core.enumeration import build_rows
from marcus.core.substituents import Fragment, resolve


def _key(smiles: str) -> str:
    return Chem.MolToInchiKey(Chem.MolFromSmiles(smiles))


def measure(path: Path) -> dict:
    gold = json.loads(path.read_text())
    totals = {"right": 0, "wrong": 0, "not_built": 0}
    print(f"\n== {gold['paper']}")
    for sc in gold["scaffolds"]:
        print(f"  -- {sc['name']}")
        for out in build_rows(sc.get("smiles"), sc.get("molfile"), sc["rows"]):
            c = out["compound"]
            want = sc["expected"].get(c)
            if "reason" in out:
                totals["not_built"] += 1
                print(f"     {c:8} could not build: {out['reason']}")
            elif want is None:
                totals["wrong"] += 1
                print(
                    f"     {c:8} WRONG: built {out['smiles']} but the gold says it must not build"
                )
            elif out["inchikey"] == _key(want):
                totals["right"] += 1
                print(f"     {c:8} right   {out['smiles']}")
            else:
                totals["wrong"] += 1
                print(f"     {c:8} WRONG   built {out['inchikey']} want {_key(want)} ({want})")
        for c in sc["expected"]:
            if c not in {r["compound"] for r in sc["rows"]}:
                print(f"     {c:8} (in the gold, not in the rows)")
    print(f"  totals: {totals}")
    return totals


def coverage(directory: Path) -> float:
    values = [
        v
        for f in sorted(directory.glob("*.json"))
        for s in json.loads(f.read_text()).get("scaffolds", [])
        for r in s.get("rows", [])
        for v in r.get("groups", {}).values()
    ]
    ok = sum(isinstance(resolve(v), Fragment) for v in values)
    share = ok / len(values) if values else 0.0
    print(f"\ncoverage: {ok} of {len(values)} Phase 2 gold values resolve ({share:.1%})")
    return share


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", nargs="+", type=Path, required=True)
    ap.add_argument("--coverage", type=Path)
    args = ap.parse_args()
    wrong = 0
    grand = {"right": 0, "wrong": 0, "not_built": 0}
    for path in args.gold:
        t = measure(path)
        for k in grand:
            grand[k] += t[k]
        wrong += t["wrong"]
    print(f"\nALL: {grand}")
    if args.coverage:
        coverage(args.coverage)
    return 1 if wrong else 0


if __name__ == "__main__":
    sys.exit(main())
