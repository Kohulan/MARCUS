import os
from typing import Optional, Union, Literal, Dict, Any
from fastapi import (
    APIRouter,
    Body,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel, Field
from app.schemas.healthcheck import HealthCheck
from app.schemas.error import BadRequestModel, ErrorResponse, NotFoundModel
from app.modules.ocsr_wrapper import process_chemical_structure, save_uploaded_image
from app.config import UPLOAD_DIR, SEGMENTS_DIR, IMAGES_DIR

# Create a router for the OCSR endpoints
router = APIRouter(
    prefix="/ocsr",
    tags=["ocsr"],
    dependencies=[],
    responses={
        200: {"description": "OK"},
        400: {"description": "Bad Request", "model": BadRequestModel},
        404: {"description": "Not Found", "model": NotFoundModel},
        422: {"description": "Unprocessable Entity", "model": ErrorResponse},
    },
)


class PathInput(BaseModel):
    """Model for inputting an image path."""

    path: str = Field(..., description="Path to the chemical structure image")
    engine: Literal["decimer", "molnextr", "molscribe"] = Field(
        "decimer", description="OCSR engine to use (decimer, molnextr, or molscribe)"
    )


@router.get("/", include_in_schema=False)
@router.get(
    "/health",
    tags=["healthcheck"],
    summary="Perform a Health Check on OCSR Module",
    response_description="Return HTTP Status Code 200 (OK)",
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
    response_model=HealthCheck,
)
def get_health() -> HealthCheck:
    """Perform a Health Check.
    Endpoint to perform a health check on.
    Returns:
        HealthCheck: Returns a JSON response with the health status
    """
    return HealthCheck(status="OK")


def find_image_path(image_path: str) -> str:
    """
    Find the correct path to the image, respecting PDF directory boundaries

    Args:
        image_path: The path or filename to find

    Returns:
        str: The full valid path to the image file

    Raises:
        FileNotFoundError: If the image cannot be found
    """
    # Check if the provided path exists directly
    if os.path.exists(image_path) and os.path.isfile(image_path):
        return image_path

    # Check if it's in the IMAGES_DIR
    images_path = os.path.join(IMAGES_DIR, os.path.basename(image_path))
    if os.path.exists(images_path) and os.path.isfile(images_path):
        return images_path

    # Handle segments with respect to PDF hierarchy
    if SEGMENTS_DIR and "/all_segments/" in image_path:
        # Extract the PDF directory name from the path
        path_parts = image_path.split("/")

        # Find the PDF directory part in the path
        pdf_dir_index = -1
        for i, part in enumerate(path_parts):
            if part == "all_segments" and i > 0:
                pdf_dir_index = i - 1
                break

        if pdf_dir_index >= 0:
            # Get the PDF directory name
            pdf_directory = path_parts[pdf_dir_index]

            # Build the full path within this PDF's directory
            segment_name = os.path.basename(image_path)

            # First check exact path
            if os.path.exists(image_path) and os.path.isfile(image_path):
                return image_path

            # Then check in the PDF's all_segments directory
            pdf_segments_dir = os.path.join(SEGMENTS_DIR, pdf_directory, "all_segments")
            pdf_segment_path = os.path.join(pdf_segments_dir, segment_name)

            if os.path.exists(pdf_segment_path) and os.path.isfile(pdf_segment_path):
                return pdf_segment_path

            # If still not found, search only within this PDF's directory tree
            pdf_dir_path = os.path.join(SEGMENTS_DIR, pdf_directory)
            for root, dirs, files in os.walk(pdf_dir_path):
                if segment_name in files:
                    return os.path.join(root, segment_name)

    # If we reached here, try a global search as a fallback, but with a warning
    for root, dirs, files in os.walk(SEGMENTS_DIR):
        basename = os.path.basename(image_path)
        if basename in files:
            print(f"WARNING: Found image {basename} in {root} via fallback search")
            return os.path.join(root, basename)

    # Image not found
    raise FileNotFoundError(f"Image file not found: {image_path}")


@router.post(
    "/generate_smiles",
    summary="Generate SMILES from a chemical structure image",
    response_description="Return the SMILES string and image information",
    status_code=status.HTTP_200_OK,
)
async def generate_smiles(
    image_file: Optional[UploadFile] = File(
        None, description="Chemical structure image file"
    ),
    image_path: Optional[str] = Form(
        None, description="Path to existing chemical structure image"
    ),
    engine: Literal["decimer", "molnextr", "molscribe"] = Form(
        "decimer", description="OCSR engine to use"
    ),
    hand_drawn: bool = Form(
        False, description="Whether to use the hand-drawn model (only for DECIMER)"
    ),
):
    """
    Generate a SMILES string from a chemical structure image.

    You can either upload a new image or provide the path to an existing image on the server.

    Args:
        image_file: The chemical structure image file to upload (optional)
        image_path: Path to an existing chemical structure image on the server (optional)
        engine: OCSR engine to use (decimer, molnextr, or molscribe)
        hand_drawn: Whether to use the hand-drawn model (only applicable for DECIMER)

    Returns:
        JSON: The generated SMILES string and image information
    """
    # Validate input - we need either an image file or a path
    if image_file is None and (image_path is None or not image_path.strip()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either an image file or an image path must be provided",
        )

    # Validate hand_drawn parameter - only applicable for DECIMER
    if hand_drawn and engine != "decimer":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The hand_drawn parameter is only applicable for the DECIMER engine",
        )

    try:
        # Process uploaded file if provided
        if image_file is not None:
            # Validate file type
            filename = image_file.filename.lower()
            if not any(
                filename.endswith(ext)
                for ext in [".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"]
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Uploaded file must be an image (PNG, JPG, TIFF, or BMP)",
                )

            # Read and save the uploaded file
            content = await image_file.read()
            file_path = save_uploaded_image(content, image_file.filename)
        else:
            # Use the provided path and try to find the actual file
            try:
                file_path = find_image_path(image_path)
            except FileNotFoundError:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Image file not found: {image_path}",
                )

        # Process the image
        result = process_chemical_structure(
            file_path=file_path,
            engine=engine,
            output_type="smiles",
            hand_drawn=hand_drawn,
        )

        # Add file path to result
        result["file_path"] = os.path.basename(file_path)

        return result

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating SMILES: {str(e)}",
        )


@router.post(
    "/generate_molfile",
    summary="Generate a molfile from a chemical structure image",
    response_description="Return the molfile and image information",
    status_code=status.HTTP_200_OK,
)
async def generate_molfile(
    image_file: Optional[UploadFile] = File(
        None, description="Chemical structure image file"
    ),
    image_path: Optional[str] = Form(
        None, description="Path to existing chemical structure image"
    ),
    engine: Literal["molnextr", "molscribe"] = Form(
        "molnextr", description="OCSR engine to use"
    ),
):
    """
    Generate a molfile from a chemical structure image.

    You can either upload a new image or provide the path to an existing image on the server.
    Note: Only MolNexTR and MolScribe engines support molfile generation.

    Args:
        image_file: The chemical structure image file to upload (optional)
        image_path: Path to an existing chemical structure image on the server (optional)
        engine: OCSR engine to use (only molnextr and molscribe are supported for molfile generation)

    Returns:
        JSON: The generated molfile and image information
    """
    # Validate input - we need either an image file or a path
    if image_file is None and (image_path is None or not image_path.strip()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either an image file or an image path must be provided",
        )

    try:
        # Validate engine (only molnextr and molscribe support molfile generation)
        if engine not in ["molnextr", "molscribe"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only the MolNexTR and MolScribe engines support molfile generation",
            )

        # Process uploaded file if provided
        if image_file is not None:
            # Validate file type
            filename = image_file.filename.lower()
            if not any(
                filename.endswith(ext)
                for ext in [".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"]
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Uploaded file must be an image (PNG, JPG, TIFF, or BMP)",
                )

            # Read and save the uploaded file
            content = await image_file.read()
            file_path = save_uploaded_image(content, image_file.filename)
        else:
            # Use the provided path and try to find the actual file
            try:
                file_path = find_image_path(image_path)
            except FileNotFoundError:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Image file not found: {image_path}",
                )

        # Process the image
        result = process_chemical_structure(
            file_path=file_path, engine=engine, output_type="molfile"
        )

        # Add file path to result
        result["file_path"] = os.path.basename(file_path)

        return result

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating molfile: {str(e)}",
        )


@router.post(
    "/generate_both",
    summary="Generate both SMILES and molfile from a chemical structure image",
    response_description="Return both SMILES and molfile along with image information",
    status_code=status.HTTP_200_OK,
)
async def generate_both(
    image_file: Optional[UploadFile] = File(
        None, description="Chemical structure image file"
    ),
    image_path: Optional[str] = Form(
        None, description="Path to existing chemical structure image"
    ),
    engine: Literal["decimer", "molnextr", "molscribe"] = Form(
        "molnextr", description="OCSR engine to use"
    ),
    hand_drawn: bool = Form(
        False, description="Whether to use the hand-drawn model (only for DECIMER)"
    ),
):
    """
    Generate both SMILES and molfile from a chemical structure image.

    You can either upload a new image or provide the path to an existing image on the server.
    Note: For the 'decimer' engine, only SMILES will be generated. MolNexTR and MolScribe
    engines provide both SMILES and molfile. The hand_drawn parameter is only applicable
    when using the DECIMER engine.

    Args:
        image_file: The chemical structure image file to upload (optional)
        image_path: Path to an existing chemical structure image on the server (optional)
        engine: OCSR engine to use (decimer, molnextr, or molscribe)
        hand_drawn: Whether to use the hand-drawn model (only applicable for DECIMER)

    Returns:
        JSON: The generated SMILES, molfile (if available), and image information
    """
    # Validate input - we need either an image file or a path
    if image_file is None and (image_path is None or not image_path.strip()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either an image file or an image path must be provided",
        )

    # Validate hand_drawn parameter - only applicable for DECIMER
    if hand_drawn and engine != "decimer":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The hand_drawn parameter is only applicable for the DECIMER engine",
        )

    try:
        # Process uploaded file if provided
        if image_file is not None:
            # Validate file type
            filename = image_file.filename.lower()
            if not any(
                filename.endswith(ext)
                for ext in [".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"]
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Uploaded file must be an image (PNG, JPG, TIFF, or BMP)",
                )

            # Read and save the uploaded file
            content = await image_file.read()
            file_path = save_uploaded_image(content, image_file.filename)
        else:
            # Use the provided path and try to find the actual file
            try:
                file_path = find_image_path(image_path)
            except FileNotFoundError:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Image file not found: {image_path}",
                )

        # Process the image
        result = process_chemical_structure(
            file_path=file_path,
            engine=engine,
            output_type="both",
            hand_drawn=hand_drawn,
        )

        # Add file path to result
        result["file_path"] = os.path.basename(file_path)

        return result

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating results: {str(e)}",
        )


# Keep the get_image endpoint as is
@router.get(
    "/get_image/{image_name}",
    summary="Get a specific chemical structure image",
    response_description="Return the requested image",
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "content": {"image/*": {}},
            "description": "Return the image",
        }
    },
)
async def get_image(
    image_name: str,
):
    """
    Get a specific chemical structure image.

    Args:
        image_name: The image filename

    Returns:
        FileResponse: The requested image file
    """
    try:
        # Validate the image name to prevent directory traversal
        if ".." in image_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid image name"
            )

        # Find the image using the find_image_path function
        try:
            image_path = find_image_path(image_name)
        except FileNotFoundError:
            # Fall back to checking just in IMAGES_DIR
            image_path = os.path.join(IMAGES_DIR, image_name)
            if not os.path.exists(image_path) or not os.path.isfile(image_path):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Image not found: {image_name}",
                )

        # Determine media type based on file extension
        ext = os.path.splitext(image_name)[1].lower()
        media_type = None

        if ext in [".jpg", ".jpeg"]:
            media_type = "image/jpeg"
        elif ext == ".png":
            media_type = "image/png"
        elif ext in [".tif", ".tiff"]:
            media_type = "image/tiff"
        elif ext == ".bmp":
            media_type = "image/bmp"
        else:
            media_type = "application/octet-stream"

        return FileResponse(
            image_path, media_type=media_type, filename=os.path.basename(image_path)
        )

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving image: {str(e)}",
        )


@router.post(
    "/generate_with_depiction",
    summary="Generate chemical notation with depiction from an image",
    response_description="Return both chemical notation and depiction",
    status_code=status.HTTP_200_OK,
)
async def generate_with_depiction(
    image_file: Optional[UploadFile] = File(
        None, description="Chemical structure image file"
    ),
    image_path: Optional[str] = Form(
        None, description="Path to existing chemical structure image"
    ),
    engine: Literal["decimer", "molnextr", "molscribe"] = Form(
        "molnextr", description="OCSR engine to use"
    ),
    output_type: Literal["smiles", "molfile", "both"] = Form(
        "both", description="Type of chemical notation to generate"
    ),
    hand_drawn: bool = Form(
        False, description="Whether to use the hand-drawn model (only for DECIMER)"
    ),
    depict_engine: Literal["cdk", "rdkit"] = Form(
        "rdkit", description="Depiction engine to use"
    ),
    depict_width: int = Form(512, description="Width of the depiction in pixels"),
    depict_height: int = Form(512, description="Height of the depiction in pixels"),
    depict_format: Literal["svg", "png", "base64"] = Form(
        "svg", description="Output format for depiction"
    ),
):
    """
    Generate both chemical notation and a depiction from a chemical structure image.

    This endpoint combines OCSR functionality with molecular depiction, providing
    both the extracted chemical notation (SMILES/molfile) and a visual representation
    of the recognized structure.

    Args:
        image_file: The chemical structure image file to upload (optional)
        image_path: Path to an existing chemical structure image on the server (optional)
        engine: OCSR engine to use (decimer, molnextr, or molscribe)
        output_type: Type of chemical notation to generate (smiles, molfile, or both)
        hand_drawn: Whether to use the hand-drawn model (only applicable for DECIMER)
        depict_engine: Engine to use for molecular depiction (cdk or rdkit)
        depict_width: Width of the depiction in pixels
        depict_height: Height of the depiction in pixels
        depict_format: Output format for the depiction (svg, png, or base64)

    Returns:
        JSON: Object containing the recognition results and molecular depiction
    """
    try:
        # First, use the existing OCSR functionality to get chemical notation
        ocsr_result = await generate_both(
            image_file=image_file,
            image_path=image_path,
            engine=engine,
            hand_drawn=hand_drawn,
        )

        # Extract SMILES and molfile from the result
        smiles = ocsr_result.get("smiles", "")
        molfile = ocsr_result.get("molfile", "")

        # Use the depiction module to generate a depiction
        from app.modules.depiction import generate_depiction

        depiction_result = generate_depiction(
            smiles=smiles,
            molfile=molfile if output_type in ["molfile", "both"] else None,
            engine=depict_engine,
            mol_size=(depict_width, depict_height),
            rotate=0,  # Default to no rotation for OCSR results
            kekulize=True,
            cip=True,
            unicolor=False,
            highlight="",
            transparent=False,
            format=depict_format,
        )

        # Format the result for the response
        result = {
            **ocsr_result,  # Include all original OCSR results
            "depiction": {"format": depict_format, "engine": depict_engine},
        }

        # Add the depiction based on format
        if depict_format == "svg":
            result["depiction"]["svg"] = depiction_result["depiction"]
        elif depict_format == "png":
            import base64

            # Convert binary PNG to base64 for JSON response
            result["depiction"]["base64"] = base64.b64encode(
                depiction_result["depiction"]
            ).decode("utf-8")
        else:  # already base64
            result["depiction"]["base64"] = depiction_result["depiction"]

        return result

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating results with depiction: {str(e)}",
        )
