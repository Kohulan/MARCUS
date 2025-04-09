from __future__ import annotations
import json
import os
import uuid
import datetime
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Body, HTTPException, status
from app.schemas.healthcheck import HealthCheck
from app.modules.openai_wrapper import (
    get_extracted_json,
    get_extracted_positions,
    get_spans,
)
from app.config import UPLOAD_DIR

# Create a directory for OpenAI annotation results
OPENAI_RESULTS_DIR = os.path.join(UPLOAD_DIR, "openai_results")
os.makedirs(OPENAI_RESULTS_DIR, exist_ok=True)

router = APIRouter(
    prefix="/openai",
    tags=["openai_annotation"],
    dependencies=[],
    responses={
        200: {"description": "OK"},
        400: {"description": "Bad Request"},
        500: {"description": "Internal Server Error"},
    },
)


@router.get("/", include_in_schema=False)
@router.get(
    "/health",
    tags=["healthcheck"],
    summary="Perform a Health Check on OpenAI Annotation Module",
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


def save_extraction_result(
    input_text: str, extracted_json: Any, positions: List[Dict[str, Any]]
) -> str:
    """
    Save the extraction results to a local JSON file with consistent naming.

    Args:
        input_text: The original text input
        extracted_json: The extracted JSON result
        positions: The extracted positions

    Returns:
        str: The filename of the saved result
    """
    # Create a hash of the input text to ensure same text gets same filename
    import hashlib

    text_hash = hashlib.md5(input_text.encode()).hexdigest()[:8]

    # Create a filename based on content hash rather than timestamp
    filename = f"extraction_{text_hash}.json"
    file_path = os.path.join(OPENAI_RESULTS_DIR, filename)

    # Check if file already exists
    if os.path.exists(file_path):
        # Read existing file to check if it contains the same input text
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
                if existing_data.get("input_text") == input_text:
                    # Return existing filename if data matches
                    return filename
        except:
            pass  # If reading fails, overwrite file

    # Create a data structure to save
    result_data = {
        "timestamp": datetime.datetime.now().isoformat(),
        "input_text": input_text,
        "extracted_json": extracted_json,
        "positions": positions,
    }

    # Save to file
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2)

    return filename


@router.post(
    "/extract_json",
    summary="Extract JSON from text using OpenAI",
    response_description="Return extracted JSON data",
    status_code=status.HTTP_200_OK,
)
async def extract_json(
    text: str = Body(..., description="Text to process", embed=True),
):
    """
    Extract structured JSON data from text using OpenAI.

    Args:
        text: The text to process

    Returns:
        JSON: The extracted structured data
    """
    try:
        result = get_extracted_json(text)

        # Get positions to save alongside the JSON
        positions = get_extracted_positions(text)

        # Save results locally
        saved_filename = save_extraction_result(text, result, positions)

        # Include the saved filename in the response
        result_with_filename = {"result": result, "saved_as": saved_filename}

        return result_with_filename

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error during JSON extraction: {str(e)}",
        )


@router.post(
    "/extract_positions",
    summary="Extract entity positions from text using OpenAI",
    response_description="Return positions of extracted entities",
    status_code=status.HTTP_200_OK,
)
async def extract_positions(
    text: str = Body(..., description="Text to process", embed=True),
):
    """
    Extract entity positions from text using OpenAI.

    Args:
        text: The text to process

    Returns:
        JSON: A list of entity positions with start and end offsets
    """
    try:
        positions = get_extracted_positions(text)

        # Get JSON to save alongside the positions
        extracted_json = get_extracted_json(text)

        # Save results locally
        saved_filename = save_extraction_result(text, extracted_json, positions)

        # Include the saved filename in the response
        result_with_filename = {"positions": positions, "saved_as": saved_filename}

        return result_with_filename

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error during position extraction: {str(e)}",
        )


@router.post(
    "/extract_all",
    summary="Extract both JSON and positions from text using OpenAI",
    response_description="Return both extracted JSON and positions",
    status_code=status.HTTP_200_OK,
)
async def extract_all(
    text: str = Body(..., description="Text to process", embed=True),
):
    """
    Extract both JSON data and entity positions from text using OpenAI.

    Args:
        text: The text to process

    Returns:
        JSON: Both the extracted JSON and positions
    """
    try:
        extracted_text, positions = get_spans(text)

        # Try to parse extracted_text as JSON
        try:
            json_data = json.loads(extracted_text) if extracted_text else {}
        except:
            json_data = {"raw_text": extracted_text}

        # Save results locally
        saved_filename = save_extraction_result(text, json_data, positions)

        # Include the saved filename in the response
        result = {
            "extracted_data": json_data,
            "positions": positions,
            "saved_as": saved_filename,
        }

        return result

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error during extraction: {str(e)}",
        )


@router.get(
    "/list_extractions",
    summary="List all saved extractions",
    response_description="Return a list of saved extraction results",
    status_code=status.HTTP_200_OK,
)
async def list_extractions():
    """
    List all saved extraction results.

    Returns:
        JSON: A list of extraction result filenames and metadata
    """
    try:
        extraction_files = []
        for filename in os.listdir(OPENAI_RESULTS_DIR):
            if filename.startswith("extraction_") and filename.endswith(".json"):
                file_path = os.path.join(OPENAI_RESULTS_DIR, filename)
                file_stats = os.stat(file_path)

                # Try to read some minimal metadata
                metadata = {}
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        metadata = {
                            "timestamp": data.get("timestamp", ""),
                            "input_text_preview": data.get("input_text", "")[:100]
                            + "..."
                            if len(data.get("input_text", "")) > 100
                            else data.get("input_text", ""),
                        }
                except:
                    pass

                extraction_files.append(
                    {
                        "filename": filename,
                        "size_bytes": file_stats.st_size,
                        "created_time": file_stats.st_ctime,
                        **metadata,
                    }
                )

        # Sort by creation time (newest first)
        extraction_files.sort(key=lambda x: x["created_time"], reverse=True)

        return {"extraction_files": extraction_files}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing extractions: {str(e)}",
        )


@router.get(
    "/get_extraction/{filename}",
    summary="Get a specific extraction result",
    response_description="Return the specified extraction result",
    status_code=status.HTTP_200_OK,
)
async def get_extraction(filename: str):
    """
    Get a specific saved extraction result.

    Args:
        filename: The filename of the extraction result

    Returns:
        JSON: The complete extraction result
    """
    try:
        # Validate the filename to prevent directory traversal
        if (
            ".." in filename
            or not filename.startswith("extraction_")
            or not filename.endswith(".json")
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename"
            )

        file_path = os.path.join(OPENAI_RESULTS_DIR, filename)

        # Check if the file exists
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Extraction result not found: {filename}",
            )

        # Read and return the file
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return data

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving extraction result: {str(e)}",
        )
