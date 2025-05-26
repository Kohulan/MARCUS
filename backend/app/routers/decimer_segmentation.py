from __future__ import annotations
import os
import uuid
import re
from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    status,
    UploadFile,
    File,
    Form,
)
from fastapi.responses import FileResponse
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
    """
    Perform a health check on the DECIMER segmentation module.

    This endpoint verifies that the DECIMER segmentation service is operational
    and ready to process requests. Used for container orchestration and monitoring.

    Returns:
        HealthCheck: JSON response with service health status.

    Example:
        >>> response = get_health()
        >>> print(response.status)
        "OK"
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
    Extract DOI (Digital Object Identifier) from an uploaded PDF file.

    Processes the uploaded PDF to extract its DOI using the pdf2doi library.
    Falls back to using the filename if no DOI is found in the document.

    Args:
        pdf_file (UploadFile): The PDF file to process for DOI extraction.

    Returns:
        dict: JSON response containing the extracted DOI or fallback filename.

    Raises:
        HTTPException:
            - 400: If uploaded file is not a PDF
            - 500: If DOI extraction fails

    Example:
        >>> result = await extract_doi(pdf_file)
        >>> print(result['doi'])
        "10.1021/acs.jcim.2c00934"
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
    Extract chemical structure segments from an uploaded PDF file using DECIMER.

    Processes the PDF to identify and extract chemical structure images with
    bounding box information. Organizes segments in structured directories.

    Args:
        pdf_file (UploadFile): The PDF file containing chemical structures.
        collect_all (bool): Whether to collect all segments in a common directory. Defaults to True.

    Returns:
        dict: JSON response containing:
              - segments_extracted: Success status
              - segments_already_existed: Whether segments existed before processing
              - segments_count: Number of extracted segments
              - segments_directory: Relative path to segments directory
              - pdf_filename: Sanitized filename

    Raises:
        HTTPException:
            - 400: If uploaded file is not a PDF
            - 500: If segmentation processing fails

    Example:
        >>> result = await extract_segments(pdf_file, collect_all=True)
        >>> print(f"Found {result['segments_count']} segments")
        Found 8 segments
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
    List all available chemical structure segment directories.

    Scans the segments directory to find all processed PDF directories,
    counting the number of segments in each and checking for organized structure.

    Returns:
        dict: JSON response containing:
              - segment_directories: List of directory information including:
                - directory: Directory name
                - segments_count: Number of segments found
                - has_all_segments: Whether organized structure exists

    Raises:
        HTTPException: 500 if directory listing fails

    Example:
        >>> result = await list_segments()
        >>> print(len(result['segment_directories']))
        5
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
    Retrieve a specific chemical structure segment image file.

    Serves individual segment images from the organized directory structure,
    handling both direct paths and all_segments subdirectory organization.

    Args:
        directory (str): The segment directory name (PDF-based directory).
        image_name (str): The segment image filename or relative path.

    Returns:
        FileResponse: The requested segment image as PNG file response.

    Raises:
        HTTPException:
            - 400: Invalid directory or image name (prevents directory traversal)
            - 404: Image file not found
            - 500: File retrieval error

    Example:
        >>> response = await get_segment_image("chemistry_paper", "page_0_1_segmented.png")
        >>> print(response.media_type)
        "image/png"
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
    """
    Count the number of segmented images in a directory structure.

    Helper function that handles different directory organizations including
    all_segments subdirectories and individual segment directories.

    Args:
        directory_path (str): Path to the directory to count segments in.

    Returns:
        int: Number of segmented PNG images found. Returns 0 if directory
             doesn't exist or counting fails.

    Example:
        >>> count = _count_segments("/segments/chemistry_paper")
        >>> print(count)
        12
    """
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
    List all segmented image files in a specific directory or subdirectory.

    Provides directory browsing functionality for segment files with
    security validation to prevent directory traversal attacks.

    Args:
        directory (str): The base segment directory name.
        subdirectory (str, optional): Optional subdirectory within the base directory.

    Returns:
        dict: JSON response containing:
              - files: List of segmented PNG filenames in the directory

    Raises:
        HTTPException:
            - 400: Invalid directory names (prevents directory traversal)
            - 404: Directory not found
            - 500: Directory listing error

    Example:
        >>> result = await list_directory("chemistry_paper", "all_segments")
        >>> print(len(result['files']))
        8
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
    Generate a PDF page image with a specific chemical segment highlighted.

    Creates a visual representation showing the original PDF page with the
    specified chemical structure segment highlighted using a green overlay.

    Args:
        segment_filename (str): The segment filename in format "page_{page_num}_{segment_num}_segmented.png".
        pdf_filename (str): The original PDF filename containing the segment.

    Returns:
        FileResponse: PNG image of the PDF page with highlighted segment area.

    Raises:
        HTTPException:
            - 400: Invalid segment filename format
            - 404: PDF or segment not found
            - 500: Image generation error

    Example:
        >>> response = await get_highlighted_page("page_0_1_segmented.png", "chemistry_paper.pdf")
        >>> print(response.filename)
        "highlighted_segment-0-1_a1b2c3d4.png"
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
