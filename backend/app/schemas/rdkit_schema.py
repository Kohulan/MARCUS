from __future__ import annotations

from typing import List, Dict, Any
from pydantic import BaseModel


# Define request and response models
class SmilesComparisonRequest(BaseModel):
    smiles_list: List[str]
    engine_names: List[str]


class MolfilesMCSRequest(BaseModel):
    molfiles: List[str]
    engine_names: List[str]


class MCSResponse(BaseModel):
    mcs_smarts: str
    atom_count: int
    bond_count: int
    original_molecules: List[Dict[str, Any]]


class SimilarityMatrix(BaseModel):
    matrix: List[List[float]]
    engine_names: List[str]
    identical: bool
    agreement_summary: Dict[str, Any]