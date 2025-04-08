from __future__ import annotations

import os
import io
from typing import Optional, Union, Literal, Dict, Any, List, Tuple
from fastapi import APIRouter, Body, File, Form, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from app.schemas.healthcheck import HealthCheck
from app.schemas.error import BadRequestModel, ErrorResponse, NotFoundModel
from app.modules.depiction import generate_depiction

# Create the router
router = APIRouter(
    prefix="/depiction",
    tags=["depiction"],
    dependencies=[],
    responses={
        200: {"description": "OK"},
        400: {"description": "Bad Request", "model": BadRequestModel},
        404: {"description": "Not Found", "model": NotFoundModel},
        422: {"description": "Unprocessable Entity", "model": ErrorResponse},
    },
)

# Pydantic models for request validation
class DepictionRequest(BaseModel):
    """Model for depiction request parameters."""
    smiles: Optional[str] = Field(None, description="SMILES string to depict")
    molfile: Optional[str] = Field(None, description="Molfile string to depict")
    useMolfileDirectly: Optional[bool] = Field(False, description="Whether to use molfile directly with CDK without generating coordinates")
    # Engine is ignored - always uses CDK
    engine: Literal["cdk"] = Field("cdk", description="Depiction engine to use (always CDK)")
    width: int = Field(512, description="Width of the depiction in pixels", ge=100, le=2000)
    height: int = Field(512, description="Height of the depiction in pixels", ge=100, le=2000)
    rotate: float = Field(0, description="Rotation angle in degrees", ge=0, lt=360)
    kekulize: bool = Field(True, description="Whether to kekulize the molecule")
    cip: bool = Field(True, description="Whether to display CIP stereochemistry annotations")
    unicolor: bool = Field(False, description="Whether to use a single color for all atoms")
    highlight: str = Field("", description="SMARTS pattern to highlight")
    transparent: bool = Field(False, description="Whether to use transparent background")
    format: Literal["svg", "png", "base64"] = Field("svg", description="Output format")

# Health check endpoint
@router.get("/", include_in_schema=False)
@router.get(
    "/health",
    tags=["healthcheck"],
    summary="Perform a Health Check on Depiction Module",
    response_description="Return HTTP Status Code 200 (OK)",
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
    response_model=HealthCheck,
)
def get_health() -> HealthCheck:
    """Perform a Health Check.
    Endpoint to perform a health check on the Depiction module.
    Returns:
        HealthCheck: Returns a JSON response with the health status
    """
    return HealthCheck(status="OK")

# Depiction endpoint (JSON body)
@router.post(
    "/generate",
    summary="Generate a molecular depiction",
    response_description="Return molecular depiction",
    status_code=status.HTTP_200_OK,
)
async def create_depiction(
    request: DepictionRequest
):
    """
    Generate a molecular depiction using the specified parameters.
    
    Provide either a SMILES string or a molfile (or both).
    
    Args:
        request: Depiction request parameters
        
    Returns:
        Response with the generated depiction in the requested format
    """
    try:
        # Validate input - require either SMILES or molfile
        if not request.smiles and not request.molfile:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either SMILES or molfile must be provided"
            )
        
        # Generate depiction - always use CDK
        result = generate_depiction(
            smiles=request.smiles,
            molfile=request.molfile,
            engine="cdk",  # Always use CDK
            mol_size=(request.width, request.height),
            rotate=request.rotate,
            kekulize=request.kekulize,
            cip=request.cip,
            unicolor=request.unicolor,
            highlight=request.highlight,
            transparent=request.transparent,
            format=request.format,
            use_molfile_directly=request.useMolfileDirectly
        )
        
        # Return response based on format
        if request.format == "svg":
            return Response(
                content=result["depiction"],
                media_type="image/svg+xml"
            )
        elif request.format == "png":
            return Response(
                content=result["depiction"],
                media_type="image/png"
            )
        else:  # base64
            return {
                "format": "base64",
                "engine": "cdk",
                "data": result["depiction"]
            }
    
    except HTTPException:
        raise
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating depiction: {str(e)}"
        )

# Depiction endpoint (form data)
@router.post(
    "/visualize",
    summary="Visualize a molecular structure",
    response_description="Return molecular visualization",
    status_code=status.HTTP_200_OK,
)
async def visualize_structure(
    smiles: Optional[str] = Form(None, description="SMILES string to depict"),
    molfile: Optional[str] = Form(None, description="Molfile string to depict"),
    useMolfileDirectly: Optional[bool] = Form(False, description="Whether to use molfile directly with CDK without generating coordinates"),
    # Engine is ignored - always uses CDK
    engine: Literal["cdk"] = Form("cdk", description="Depiction engine to use (always CDK)"),
    width: int = Form(512, description="Width of the depiction in pixels"),
    height: int = Form(512, description="Height of the depiction in pixels"),
    rotate: float = Form(0, description="Rotation angle in degrees"),
    kekulize: bool = Form(True, description="Whether to kekulize the molecule"),
    cip: bool = Form(True, description="Whether to display CIP stereochemistry annotations"),
    unicolor: bool = Form(False, description="Whether to use a single color for all atoms"),
    highlight: str = Form("", description="SMARTS pattern to highlight"),
    transparent: bool = Form(False, description="Whether to use transparent background"),
    format: Literal["svg", "png", "base64"] = Form("svg", description="Output format")
):
    """
    Visualize a molecular structure using form data.
    
    This endpoint is suitable for direct form submissions and browser use.
    Provide either a SMILES string or a molfile (or both).
    
    Args:
        Various form fields for depiction parameters
        
    Returns:
        Response with the generated depiction in the requested format
    """
    try:
        # Validate input - require either SMILES or molfile
        if not smiles and not molfile:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either SMILES or molfile must be provided"
            )
        
        # Generate depiction - always use CDK
        result = generate_depiction(
            smiles=smiles,
            molfile=molfile,
            engine="cdk",  # Always use CDK
            mol_size=(width, height),
            rotate=rotate,
            kekulize=kekulize,
            cip=cip,
            unicolor=unicolor,
            highlight=highlight,
            transparent=transparent,
            format=format,
            use_molfile_directly=useMolfileDirectly
        )
        
        # Return response based on format
        if format == "svg":
            return Response(
                content=result["depiction"],
                media_type="image/svg+xml"
            )
        elif format == "png":
            return Response(
                content=result["depiction"],
                media_type="image/png"
            )
        else:  # base64
            return {
                "format": "base64",
                "engine": "cdk",
                "data": result["depiction"]
            }
    
    except HTTPException:
        raise
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating depiction: {str(e)}"
        )

# Endpoint to integrate with OCSR results
@router.post(
    "/from_ocsr",
    summary="Generate depictions from OCSR results",
    response_description="Return depictions for chemical structures",
    status_code=status.HTTP_200_OK,
)
async def depict_from_ocsr(
    smiles: Optional[str] = Form(None, description="SMILES string from OCSR"),
    molfile: Optional[str] = Form(None, description="Molfile string from OCSR (if available)"),
    # Engine is ignored - always uses CDK
    engine: Literal["cdk"] = Form("cdk", description="Depiction engine to use (always CDK)"),
    width: int = Form(512, description="Width of the depiction in pixels"),
    height: int = Form(512, description="Height of the depiction in pixels"),
    use_molfile: bool = Form(True, description="Whether to use molfile when available"),
    cip: bool = Form(True, description="Whether to display CIP stereochemistry annotations"),
    format: Literal["svg", "png", "base64"] = Form("svg", description="Output format")
):
    """
    Generate depictions from OCSR (Optical Chemical Structure Recognition) results.
    
    This endpoint is designed to work with the output from DECIMER or MolNexTR.
    If use_molfile is True and molfile is provided, it will use the molfile for depiction.
    Otherwise, it will use the SMILES string.
    
    Args:
        Various form fields for OCSR results and depiction parameters
        
    Returns:
        Response with the generated depiction in the requested format
    """
    try:
        # Validate input
        if not smiles and not molfile:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either SMILES or molfile must be provided"
            )
        
        # Determine which input to use based on parameters
        use_smiles = smiles
        use_molfile = molfile if use_molfile and molfile else None
        
        # Generate depiction - always use CDK
        result = generate_depiction(
            smiles=use_smiles,
            molfile=use_molfile,
            engine="cdk",  # Always use CDK
            mol_size=(width, height),
            rotate=0,  # Default to no rotation for OCSR results
            kekulize=True,  # Default to kekulize for OCSR results
            cip=cip,
            unicolor=False,  # Use colored atoms for better visualization
            highlight="",
            transparent=False,
            format=format,
            use_molfile_directly=True if use_molfile else False  # Use molfile directly if available
        )
        
        # Return response based on format
        if format == "svg":
            return Response(
                content=result["depiction"],
                media_type="image/svg+xml"
            )
        elif format == "png":
            return Response(
                content=result["depiction"],
                media_type="image/png"
            )
        else:  # base64
            return {
                "format": "base64",
                "engine": "cdk",
                "data": result["depiction"],
                "source": "molfile" if use_molfile else "smiles"
            }
    
    except HTTPException:
        raise
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating depiction from OCSR results: {str(e)}"
        )

# Batch depiction endpoint
@router.post(
    "/batch",
    summary="Generate multiple depictions",
    response_description="Return multiple molecular depictions",
    status_code=status.HTTP_200_OK,
)
async def batch_depiction(
    structures: List[DepictionRequest] = Body(..., description="List of structures to depict")
):
    """
    Generate multiple molecular depictions in a single request.
    
    This endpoint is useful for creating multiple depictions at once,
    such as for gallery views or comparison tables.
    
    Args:
        structures: List of depiction requests
        
    Returns:
        JSON: List of depiction results
    """
    results = []
    
    for i, request in enumerate(structures):
        try:
            # Validate input
            if not request.smiles and not request.molfile:
                results.append({
                    "index": i,
                    "success": False,
                    "error": "Either SMILES or molfile must be provided"
                })
                continue
            
            # Generate depiction - always use CDK
            result = generate_depiction(
                smiles=request.smiles,
                molfile=request.molfile,
                engine="cdk",  # Always use CDK
                mol_size=(request.width, request.height),
                rotate=request.rotate,
                kekulize=request.kekulize,
                cip=request.cip,
                unicolor=request.unicolor,
                highlight=request.highlight,
                transparent=request.transparent,
                format=request.format,
                use_molfile_directly=request.useMolfileDirectly
            )
            
            # Add result
            results.append({
                "index": i,
                "success": True,
                "format": request.format,
                "engine": "cdk",
                "data": result["depiction"],
                "smiles": request.smiles,
                "molfile_provided": request.molfile is not None
            })
        
        except Exception as e:
            results.append({
                "index": i,
                "success": False,
                "error": str(e),
                "smiles": request.smiles,
                "molfile_provided": request.molfile is not None
            })
    
    return {"results": results}