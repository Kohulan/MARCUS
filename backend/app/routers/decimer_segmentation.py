from __future__ import annotations
import os
import shutil
import uuid
import re
from typing import List, Dict, Any, Optional
from fastapi import (
    APIRouter,
    Body,
    HTTPException,
    Query,
    status,
    UploadFile,
    File,
    Form,
)
from fastapi.responses import JSONResponse, Response, FileResponse
from app.schemas.healthcheck import HealthCheck
from app.schemas.error import BadRequestModel, ErrorResponse, NotFoundModel
from app.config import PDF_DIR, SEGMENTS_DIR
from app.modules.decimer_segmentation_wrapper import (
    get_doi_from_file,
    get_complete_segments,
    segments_exist,
    get_highlighted_segment_image,
)

router = APIRouter(
    prefix="/decimer",
    tags=["decimer_segmentation"],
    dependencies=[],
    responses={
        200: {"description": "OK"},
        400: {"description": "Bad Request", "model": BadRequestModel},
        404: {"description": "Not Found", "model": NotFoundModel},
        422: {"description": "Unprocessable Entity", "model": ErrorResponse},
    },
)


@router.get("/", include_in_schema=False)
@router.get(
    "/health",
    tags=["healthcheck"],
    summary="Perform a Health Check on DECIMER Segmentation Module",
    response_description="Return HTTP Status Code 200 (OK)",
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
    response_model=HealthCheck,
)
def get_health() -> HealthCheck:
    """Perform a Health Check.
    Endpoint to perform a health check on. This endpoint can primarily be used by Docker
    to ensure a robust container orchestration and management are in place. Other
    services that rely on the proper functioning of the API service will not deploy if this
    endpoint returns any other HTTP status code except 200 (OK).
    Returns:
        HealthCheck: Returns a JSON response with the health status
    """
    return HealthCheck(status="OK")


@router.post(
    "/extract_doi",
    summary="Extract DOI from PDF",
    response_description="Return DOI extracted from PDF",
    status_code=status.HTTP_200_OK,
)
async def extract_doi(
    pdf_file: UploadFile = File(...),
):
    """
    Upload a PDF file and extract its DOI.

    Args:
        pdf_file: The PDF file to process

    Returns:
        JSON: The extracted DOI or filename
    """
    if not pdf_file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must be a PDF",
        )

    try:
        # Generate unique filename to prevent collisions
        unique_id = str(uuid.uuid4())[:8]
        original_filename = pdf_file.filename
        filename_parts = os.path.splitext(original_filename)
        safe_filename = f"{filename_parts[0]}_{unique_id}{filename_parts[1]}"

        # Create the full file path
        file_path = os.path.join(PDF_DIR, safe_filename)

        # Save the uploaded file
        with open(file_path, "wb") as buffer:
            content = await pdf_file.read()
            buffer.write(content)

        # Process the PDF file to extract DOI
        doi_result = get_doi_from_file(file_path)

        # Keep the file for future reference
        # (you can implement a cleanup strategy if needed)

        return doi_result

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing PDF: {str(e)}",
        )


@router.post(
    "/extract_segments",
    summary="Extract chemical structure segments from PDF",
    response_description="Return information about the extracted segments",
    status_code=status.HTTP_200_OK,
)
async def extract_segments(
    pdf_file: UploadFile = File(...),
    collect_all: bool = Form(
        True, description="Whether to collect all segments in a common directory"
    ),
):
    """
    Upload a PDF file and extract chemical structure segments.

    Args:
        pdf_file: The PDF file to process
        collect_all: Whether to collect all segments in a common directory

    Returns:
        JSON: Information about the extracted segments, including directory paths
    """
    if not pdf_file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must be a PDF",
        )

    try:
        # Use original filename with basic sanitization instead of generating unique ID
        original_filename = pdf_file.filename
        # Replace spaces and special characters with underscores
        safe_filename = re.sub(r"[^\w.-]", "_", original_filename)

        # Create the full file path
        file_path = os.path.join(PDF_DIR, safe_filename)

        # Check if file already exists
        file_exists = os.path.exists(file_path)

        # Only save the file if it doesn't already exist
        if not file_exists:
            with open(file_path, "wb") as buffer:
                content = await pdf_file.read()
                buffer.write(content)
        else:
            # If the file exists but we need the content for processing
            # We don't need to read the file here as get_complete_segments will handle it
            pass

        # Check if segments already exist for this PDF
        segments_exist_result = segments_exist(file_path)
        segments_already_exist = segments_exist_result[0]

        # Process the PDF file to extract segments if they don't already exist
        segments_result = get_complete_segments(file_path, collect_all=collect_all)

        # Determine which directory to use for counting
        count_directory = None
        if (
            collect_all
            and "all_segments_directory" in segments_result
            and segments_result["all_segments_directory"]
        ):
            count_directory = segments_result["all_segments_directory"]
        elif "segment_directory" in segments_result:
            count_directory = segments_result["segment_directory"]

        # Count segments if we have a valid directory
        segments_count = 0
        if count_directory:
            segments_count = _count_segments(count_directory)

        # For API response, we return a more user-friendly structure
        # that includes the relative path to the segments directory

        # Get relative path to make it more portable
        all_segments_rel_path = None
        if (
            "all_segments_directory" in segments_result
            and segments_result["all_segments_directory"]
        ):
            try:
                all_segments_rel_path = os.path.relpath(
                    segments_result["all_segments_directory"], SEGMENTS_DIR
                )
            except:
                all_segments_rel_path = os.path.basename(
                    segments_result["all_segments_directory"]
                )

        sanitized_result = {
            "segments_extracted": True,
            "segments_already_existed": segments_result.get("segments_existed", False),
            "segments_count": segments_count,
            "segments_directory": all_segments_rel_path,
            "process_completed": True,
            "pdf_filename": safe_filename,
        }

        return sanitized_result

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing PDF: {str(e)}",
        )


@router.get(
    "/list_segments",
    summary="List available segment directories",
    response_description="Return a list of available segment directories",
    status_code=status.HTTP_200_OK,
)
async def list_segments():
    """
    List all available segment directories.

    Returns:
        JSON: A list of available segment directories
    """
    try:
        # Get all directories in the segments directory
        segment_dirs = []
        for item in os.listdir(SEGMENTS_DIR):
            item_path = os.path.join(SEGMENTS_DIR, item)
            if os.path.isdir(item_path):
                # Check if it has an all_segments directory
                all_segments_dir = os.path.join(item_path, "all_segments")

                # Count segments
                segments_count = 0
                if os.path.exists(all_segments_dir):
                    segments_count = len(
                        [
                            f
                            for f in os.listdir(all_segments_dir)
                            if f.endswith("_segmented.png")
                        ]
                    )

                segment_dirs.append(
                    {
                        "directory": item,
                        "segments_count": segments_count,
                        "has_all_segments": os.path.exists(all_segments_dir),
                    }
                )

        return {"segment_directories": segment_dirs}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing segments: {str(e)}",
        )


@router.get(
    "/get_segment_image/{directory}/{image_name:path}",
    summary="Get a specific segment image",
    response_description="Return the requested segment image",
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "content": {"image/png": {}},
            "description": "Return the segment image",
        }
    },
)
async def get_segment_image(
    directory: str,
    image_name: str,
):
    """
    Get a specific segment image.

    Args:
        directory: The segment directory name
        image_name: The image filename or path

    Returns:
        FileResponse: The requested image file
    """
    try:
        # Validate the directory and image name to prevent directory traversal
        if ".." in directory or ".." in image_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid directory or image name",
            )

        # Handle path with or without all_segments subdirectory
        if "all_segments" in image_name:
            # Path already includes all_segments
            image_path = os.path.join(SEGMENTS_DIR, directory, image_name)
        elif os.path.exists(os.path.join(SEGMENTS_DIR, directory, "all_segments")):
            # Check if all_segments exists and use it
            image_path = os.path.join(
                SEGMENTS_DIR, directory, "all_segments", image_name
            )
        else:
            # Fallback to direct path
            image_path = os.path.join(SEGMENTS_DIR, directory, image_name)

        # Check if the file exists
        if not os.path.exists(image_path) or not os.path.isfile(image_path):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Image not found: {image_path}",
            )

        return FileResponse(
            image_path, media_type="image/png", filename=os.path.basename(image_path)
        )

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving image: {str(e)}",
        )


def _count_segments(directory_path: str) -> int:
    """Helper function to count the number of segmented images in a directory"""
    if not directory_path:
        return 0

    try:
        # Check if directory_path is the "all_segments" directory itself
        if os.path.basename(directory_path) == "all_segments" and os.path.exists(
            directory_path
        ):
            return len(
                [f for f in os.listdir(directory_path) if f.endswith("_segmented.png")]
            )

        # Check if there's an "all_segments" subdirectory
        all_segments_dir = os.path.join(directory_path, "all_segments")
        if os.path.exists(all_segments_dir) and os.path.isdir(all_segments_dir):
            return len(
                [
                    f
                    for f in os.listdir(all_segments_dir)
                    if f.endswith("_segmented.png")
                ]
            )

        # If all_segments doesn't exist, try counting in individual segment directories
        count = 0
        # Look for directories ending with _segments
        for item in os.listdir(directory_path):
            segment_dir_path = os.path.join(directory_path, item)
            if item.endswith("_segments") and os.path.isdir(segment_dir_path):
                count += len(
                    [
                        f
                        for f in os.listdir(segment_dir_path)
                        if f.endswith("_segmented.png")
                    ]
                )
        return count
    except Exception as e:
        print(f"Error counting segments: {str(e)}")
        return 0


@router.get(
    "/list_directory/{directory}/{subdirectory}",
    summary="List files in a specific directory",
    response_description="Return a list of files in the specified directory",
    status_code=status.HTTP_200_OK,
)
async def list_directory(directory: str, subdirectory: str = None):
    """
    List all files in the specified directory.

    Args:
        directory: The base directory name
        subdirectory: Optional subdirectory

    Returns:
        JSON: A list of files in the directory
    """
    try:
        # Validate to prevent directory traversal
        if ".." in directory or (subdirectory and ".." in subdirectory):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid directory or subdirectory name",
            )

        # Construct the path
        dir_path = os.path.join(SEGMENTS_DIR, directory)
        if subdirectory:
            dir_path = os.path.join(dir_path, subdirectory)

        # Check if the directory exists
        if not os.path.exists(dir_path) or not os.path.isdir(dir_path):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Directory not found: {directory}/{subdirectory if subdirectory else ''}",
            )

        # Get all files with _segmented.png suffix
        files = [f for f in os.listdir(dir_path) if f.endswith("_segmented.png")]

        return {"files": files}

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing directory: {str(e)}",
        )


@router.get(
    "/get_highlighted_page/{segment_filename}",
    summary="Get PDF page with a specific segment highlighted",
    response_description="Return the PDF page image with highlighted segment",
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "content": {"image/png": {}},
            "description": "Return the page image with highlighted segment",
        }
    },
)
async def get_highlighted_page(
    segment_filename: str, pdf_filename: str = Query(..., description="PDF filename")
):
    """
    Get a PDF page with a specific segment highlighted.

    Args:
        segment_filename: The segment filename (e.g. page_1_10_segmented.png)
        pdf_filename: The PDF file name

    Returns:
        FileResponse: The page image with highlighted segment
    """
    try:
        # Extract segment information from filename
        # Expected format: page_{page_num}_{segment_num}_segmented.png
        match = re.match(r"page_(\d+)_(\d+)_segmented\.png", segment_filename)
        if not match:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid segment filename format: {segment_filename}",
            )

        page_num = int(match.group(1))
        segment_num = int(match.group(2))
        segment_id = f"segment-{page_num}-{segment_num}"

        # Get the highlighted page image
        highlighted_image_path = get_highlighted_segment_image(segment_id, pdf_filename)

        return FileResponse(
            highlighted_image_path,
            media_type="image/png",
            filename=os.path.basename(highlighted_image_path),
        )

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting highlighted page: {str(e)}",
        )
