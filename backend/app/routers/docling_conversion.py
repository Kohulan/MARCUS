from __future__ import annotations
import os
import uuid
from typing import Literal, Union, Optional
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
from fastapi.responses import JSONResponse, Response
from app.schemas.healthcheck import HealthCheck
from app.schemas.error import BadRequestModel, ErrorResponse, NotFoundModel
from app.config import PDF_DIR
from app.modules.dockling_wrapper import (
    get_converted_document,
    extract_from_docling_document,
    combine_to_paragraph,
)

router = APIRouter(
    prefix="/docling_conversion",
    tags=["docling_conversion"],
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
    summary="Perform a Health Check on Docling Conversion Module",
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
    "/extract_json",
    summary="Extract JSON data from PDF",
    response_description="Return extracted document structure as JSON",
    status_code=status.HTTP_200_OK,
)
async def extract_pdf_json(
    pdf_file: UploadFile = File(...),
    pages: int = Form(1, description="Number of pages to process"),
):
    """
    Upload a PDF file and extract its content as a structured JSON document.

    Args:
        pdf_file: The PDF file to process
        pages: Number of pages to process (default: 1)

    Returns:
        JSON: The extracted document structure
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

        # Process the PDF file
        json_data = get_converted_document(file_path, number_of_pages=3)

        # Keep the file for future reference
        # (you can implement a cleanup strategy if needed)

        return json_data

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing PDF: {str(e)}",
        )


@router.post(
    "/extract_text",
    summary="Extract combined text from PDF",
    response_description="Return combined text extracted from PDF",
    status_code=status.HTTP_200_OK,
)
async def extract_pdf_text(
    pdf_file: UploadFile = File(...),
    pages: int = Form(1, description="Number of pages to process"),
):
    """
    Upload a PDF file and extract its content as a combined text paragraph.

    Args:
        pdf_file: The PDF file to process
        pages: Number of pages to process (default: 1)

    Returns:
        JSON: Object containing the combined text
    """
    if not pdf_file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must be a PDF",
        )

    try:
        # Use original filename without adding unique IDs
        original_filename = pdf_file.filename
        safe_filename = original_filename.replace(" ", "_")

        # Create the full file path
        file_path = os.path.join(PDF_DIR, safe_filename)

        # Check if file already exists
        if os.path.exists(file_path):
            # Use existing file
            pass
        else:
            # Save the uploaded file with original name
            with open(file_path, "wb") as buffer:
                content = await pdf_file.read()
                buffer.write(content)

        # Process the PDF file
        json_data = get_converted_document(file_path, number_of_pages=pages)
        result = extract_from_docling_document(json_data)
        combined_text = combine_to_paragraph(result)

        # Check if the extracted text has more than 10 words
        word_count = len(combined_text.split())
        if word_count <= 10:
            # Extract the whole first page instead
            # You can either use PyPDF2 directly or modify your extraction function
            from PyPDF2 import PdfReader

            reader = PdfReader(file_path)
            if len(reader.pages) > 0:
                first_page_text = reader.pages[0].extract_text()
                combined_text = first_page_text.strip()

        return {"text": combined_text, "pdf_filename": safe_filename}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing PDF: {str(e)}",
        )


@router.get(
    "/list_pdfs",
    summary="List available PDFs",
    response_description="Return a list of uploaded PDFs",
    status_code=status.HTTP_200_OK,
)
async def list_pdfs():
    """
    List all available PDF files.

    Returns:
        JSON: A list of available PDF files
    """
    try:
        # Get all PDF files
        pdf_files = []
        for item in os.listdir(PDF_DIR):
            item_path = os.path.join(PDF_DIR, item)
            if os.path.isfile(item_path) and item.lower().endswith(".pdf"):
                file_stats = os.stat(item_path)
                pdf_files.append(
                    {
                        "filename": item,
                        "size_bytes": file_stats.st_size,
                        "created_time": file_stats.st_ctime,
                    }
                )

        return {"pdf_files": pdf_files}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing PDFs: {str(e)}",
        )
