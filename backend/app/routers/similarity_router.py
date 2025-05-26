from __future__ import annotations
from fastapi import APIRouter, Body, HTTPException, status

from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit import DataStructs
from rdkit.Chem import rdFMCS
from app.schemas.rdkit_schema import (
    SmilesComparisonRequest,
    MolfilesMCSRequest,
    MCSResponse,
    SimilarityMatrix,
)


# Create the router
router = APIRouter(
    prefix="/similarity",
    tags=["similarity"],
    dependencies=[],
    responses={
        200: {"description": "OK"},
        400: {"description": "Bad Request"},
        500: {"description": "Internal Server Error"},
    },
)


@router.post(
    "/find_mcs",
    summary="Find Maximum Common Substructure between multiple molecules",
    response_description="Return MCS as SMARTS pattern for highlighting",
    status_code=status.HTTP_200_OK,
    response_model=MCSResponse,
)
async def find_mcs(request: MolfilesMCSRequest = Body(...)):
    """
    Find the Maximum Common Substructure (MCS) between a list of molfiles.

    Args:
        request: Object containing list of molfiles and engine names

    Returns:
        MCSResponse: The SMARTS pattern representing the MCS, and stats about it
    """
    try:
        if not RDKIT_AVAILABLE:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="RDKit is not available on the server",
            )

        molfiles = request.molfiles
        engine_names = request.engine_names

        # Validate input
        if len(molfiles) != len(engine_names):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Number of molfiles must match number of engine names",
            )

        if len(molfiles) < 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least 2 molfiles are required to find MCS",
            )

        # Create molecules from molfiles
        molecules = []
        valid_mols = []
        engine_to_mol = {}

        for i, molfile in enumerate(molfiles):
            engine = engine_names[i]
            mol = Chem.MolFromMolBlock(molfile, sanitize=True)

            if mol is not None:
                molecules.append(
                    {
                        "engine": engine,
                        "molecule": mol,
                        "atom_count": mol.GetNumAtoms(),
                        "bond_count": mol.GetNumBonds(),
                    }
                )
                valid_mols.append(mol)
                engine_to_mol[engine] = mol
            else:
                # Try to sanitize separately to catch errors
                try:
                    mol = Chem.MolFromMolBlock(molfile, sanitize=False)
                    Chem.SanitizeMol(mol)
                    molecules.append(
                        {
                            "engine": engine,
                            "molecule": mol,
                            "atom_count": mol.GetNumAtoms(),
                            "bond_count": mol.GetNumBonds(),
                        }
                    )
                    valid_mols.append(mol)
                    engine_to_mol[engine] = mol
                except Exception as e:
                    print(f"Error parsing molfile from {engine}: {str(e)}")

        if len(valid_mols) < 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least 2 valid molecules are required to find MCS",
            )

        # Find MCS with proper parameters
        try:
            # Find the MCS using rdFMCS (correct module name)
            mcs_result = rdFMCS.FindMCS(
                valid_mols,
                # Parameters for MCS finding
                atomCompare=rdFMCS.AtomCompare.CompareElements,
                bondCompare=rdFMCS.BondCompare.CompareOrder,
                completeRingsOnly=True,
                timeout=5,  # 5 second timeout
                matchValences=False,
            )

            if mcs_result.canceled:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="MCS calculation timed out",
                )

            # Get the MCS SMARTS pattern
            mcs_smarts = mcs_result.smartsString

            # Convert molecule data to serializable format
            mol_data = []
            for mol_info in molecules:
                mol_data.append(
                    {
                        "engine": mol_info["engine"],
                        "atom_count": mol_info["atom_count"],
                        "bond_count": mol_info["bond_count"],
                    }
                )

            return MCSResponse(
                mcs_smarts=mcs_smarts,
                atom_count=mcs_result.numAtoms,
                bond_count=mcs_result.numBonds,
                original_molecules=mol_data,
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error in MCS calculation: {str(e)}",
            )

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error finding MCS: {str(e)}",
        )


@router.post(
    "/compare_smiles",
    summary="Compare SMILES strings and calculate similarity matrix",
    response_description="Return similarity matrix and agreement summary",
    status_code=status.HTTP_200_OK,
    response_model=SimilarityMatrix,
)
async def compare_smiles(request: SmilesComparisonRequest = Body(...)):
    """
    Compare a list of SMILES strings from different OCSR engines and calculate similarity matrix.

    Args:
        request: Object containing list of SMILES strings and engine names

    Returns:
        SimilarityMatrix: Similarity matrix, engine names, and agreement summary
    """
    try:
        if not RDKIT_AVAILABLE:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="RDKit is not available on the server",
            )

        smiles_list = request.smiles_list
        engine_names = request.engine_names

        # Validate input
        if len(smiles_list) != len(engine_names):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Number of SMILES strings must match number of engine names",
            )

        # Check if all SMILES are identical
        identical = len(set(smiles_list)) == 1

        # Create molecules from SMILES
        molecules = []
        valid_indices = []
        invalid_smiles = []

        for i, smiles in enumerate(smiles_list):
            mol = Chem.MolFromSmiles(smiles)
            if mol is not None:
                molecules.append(mol)
                valid_indices.append(i)
            else:
                invalid_smiles.append({"engine": engine_names[i], "smiles": smiles})

        # Initialize similarity matrix with zeros
        n = len(engine_names)
        similarity_matrix = [[0.0 for _ in range(n)] for _ in range(n)]

        # Fill diagonal with 1.0 (self-similarity)
        for i in range(n):
            similarity_matrix[i][i] = 1.0

        # Calculate similarity matrix for valid molecules
        if len(molecules) > 1:
            # Generate ECFP4 fingerprints
            fingerprints = []
            for mol in molecules:
                fp = AllChem.GetMorganFingerprintAsBitVect(mol, 2, nBits=2048)
                fingerprints.append(fp)

            # Calculate Tanimoto similarities
            for i in range(len(valid_indices)):
                for j in range(i + 1, len(valid_indices)):
                    idx1 = valid_indices[i]
                    idx2 = valid_indices[j]
                    similarity = DataStructs.TanimotoSimilarity(
                        fingerprints[i], fingerprints[j]
                    )
                    similarity_matrix[idx1][idx2] = similarity
                    similarity_matrix[idx2][idx1] = similarity

        # Calculate agreement summary
        agreement_counts = {}
        total_comparisons = 0
        total_agreements = 0

        # Only perform agreement analysis if there are at least 2 valid molecules
        if len(molecules) >= 2:
            # Count agreements (similarity > 0.99) between pairs
            for i in range(n):
                for j in range(i + 1, n):
                    if i in valid_indices and j in valid_indices:
                        total_comparisons += 1

                        # Consider high similarity (>0.99) as agreement
                        if similarity_matrix[i][j] > 0.99:
                            total_agreements += 1
                            pair_key = f"{engine_names[i]}-{engine_names[j]}"
                            agreement_counts[pair_key] = True
                        else:
                            pair_key = f"{engine_names[i]}-{engine_names[j]}"
                            agreement_counts[pair_key] = False

        # Calculate agreement percentage
        agreement_percentage = 0
        if total_comparisons > 0:
            agreement_percentage = (total_agreements / total_comparisons) * 100

        # Create agreement summary
        agreement_summary = {
            "identical": identical,
            "agreement_percentage": agreement_percentage,
            "total_comparisons": total_comparisons,
            "total_agreements": total_agreements,
            "pair_agreements": agreement_counts,
            "invalid_smiles": invalid_smiles,
        }

        return SimilarityMatrix(
            matrix=similarity_matrix,
            engine_names=engine_names,
            identical=identical,
            agreement_summary=agreement_summary,
        )

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error calculating similarity: {str(e)}",
        )
