import os
import shutil
import uuid
import re
import cv2
import numpy as np
from typing import List, Optional, Tuple, Dict, Any
from PIL import Image
from pathlib import Path
from pdf2doi import pdf2doi
from pdf2image import convert_from_path
from fastapi import HTTPException, status

from app.config import PDF_DIR, SEGMENTS_DIR

# Dictionary to store segment metadata from recently processed PDFs
stored_segment_info = {}

try:
    from decimer_segmentation import segment_chemical_structures_from_file
except ImportError:
    # Mock function for environments without decimer_segmentation
    def segment_chemical_structures_from_file(*args, **kwargs):
        raise ImportError("decimer_segmentation package not installed")


def get_doi_from_file(filepath: str) -> Dict[str, str]:
    """Extract DOI or filename from the given file path."""
    try:
        doi_dict = pdf2doi(filepath)
        doi = doi_dict["identifier"]
        if not doi:
            doi = Path(filepath).stem
        return {"doi": doi}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error extracting DOI: {str(e)}",
        )


def create_output_directory(filepath: str) -> str:
    """Create an output directory based on the given PDF file path."""
    # Validate input file is a PDF
    if not filepath.lower().endswith(".pdf"):
        raise ValueError(f"Expected a PDF file, got: {filepath}")

    # Generate a directory name based on the filename without adding unique ID
    file_path = Path(filepath)
    file_stem = file_path.stem
    output_dir_name = file_stem

    # Create the output directory within the segments directory
    output_directory = Path(os.path.join(SEGMENTS_DIR, output_dir_name))

    # Check if directory already exists
    if output_directory.exists():
        return str(output_directory)

    # Create directory if it doesn't exist
    output_directory.mkdir(exist_ok=True)

    return str(output_directory)


def get_segments_with_bbox(
    file_path: str, poppler_path=None
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Run DECIMER segmentation with enhanced metadata including bounding boxes.

    Args:
        file_path: Path to the PDF file
        poppler_path: Path to Poppler binaries if needed

    Returns:
        Tuple[str, List[Dict]]: Base directory path and list of segment metadata
    """
    # First get the PDF images
    if file_path.lower().endswith(".pdf"):
        try:
            images = convert_from_path(file_path, 300, poppler_path=poppler_path)
            images = [np.array(image) for image in images]
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error converting PDF to images: {str(e)}",
            )
    else:
        images = [cv2.imread(file_path)]

    # Create output directory
    base_directory = create_output_directory(file_path)
    all_segments_dir = os.path.join(base_directory, "all_segments")
    os.makedirs(all_segments_dir, exist_ok=True)

    # Process each page
    segments_metadata = []
    for page_num, page_img in enumerate(images):
        try:
            # Use the segment_chemical_structures function to get segments and bboxes
            from decimer_segmentation import segment_chemical_structures

            segments, bboxes = segment_chemical_structures(
                page_img, expand=True, return_bboxes=True
            )

            # Save each segment with metadata
            for idx, segment in enumerate(segments):
                if segment.shape[0] == 0 or segment.shape[1] == 0:
                    continue

                # Generate filename
                segment_filename = f"page_{page_num}_{idx}_segmented.png"
                segment_path = os.path.join(all_segments_dir, segment_filename)

                # Save the segment image
                cv2.imwrite(segment_path, segment)

                # Extract bounding box
                y0, x0, y1, x1 = bboxes[idx]

                # Create segment metadata
                segment_id = f"segment-{page_num}-{idx}"
                segment_metadata = {
                    "segment_id": segment_id,
                    "filename": segment_filename,
                    "path": os.path.join("all_segments", segment_filename),
                    "full_path": segment_path,
                    "pageNumber": page_num,
                    "bbox": [int(x0), int(y0), int(x1), int(y1)],
                    "segmentNumber": idx + 1,
                    "pdfFilename": os.path.basename(file_path),
                }

                segments_metadata.append(segment_metadata)

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error segmenting page {page_num}: {str(e)}",
            )

    return base_directory, segments_metadata


def get_complete_segments(path_to_pdf: str, collect_all: bool = True) -> Dict[str, Any]:
    """
    Complete pipeline for PDF processing: create directory, extract pages, segment images,
    and optionally collect all segments in a common directory.

    Args:
        path_to_pdf (str): Absolute or relative path to a PDF file.
        collect_all (bool, optional): Whether to copy all segments to a common directory. Defaults to True.

    Returns:
        Dict[str, Any]: Dictionary containing paths and segment metadata
    """
    try:
        # Check if segments already exist
        segments_exist_result = segments_exist(path_to_pdf)
        segments_already_exist = segments_exist_result[0]
        existing_path = segments_exist_result[1]

        if segments_already_exist:
            segment_directory = existing_path
            # If segments already exist, try to get their metadata from stored info
            pdf_filename = os.path.basename(path_to_pdf)
            segments_metadata = stored_segment_info.get(pdf_filename, [])

            # If we don't have metadata stored, create basic entries
            if not segments_metadata:
                all_segments_dir = os.path.join(segment_directory, "all_segments")
                if os.path.exists(all_segments_dir):
                    # Create minimal metadata from filenames
                    for segment_file in os.listdir(all_segments_dir):
                        if segment_file.endswith("_segmented.png"):
                            parts = segment_file.split("_")
                            if len(parts) >= 3 and parts[0] == "page":
                                try:
                                    page_num = int(parts[1])
                                    idx = int(parts[2])
                                    segment_id = f"segment-{page_num}-{idx}"

                                    segment_metadata = {
                                        "segment_id": segment_id,
                                        "filename": segment_file,
                                        "path": os.path.join(
                                            "all_segments", segment_file
                                        ),
                                        "full_path": os.path.join(
                                            all_segments_dir, segment_file
                                        ),
                                        "pageNumber": page_num,
                                        "segmentNumber": idx + 1,
                                        "pdfFilename": pdf_filename,
                                        # We don't have bbox info for existing segments without
                                        # reprocessing, so use a default that encompasses the whole page
                                        "bbox": [0, 0, 1000, 1000],
                                    }

                                    segments_metadata.append(segment_metadata)
                                except ValueError:
                                    continue
        else:
            # Run the segmentation with bounding box collection
            segment_directory, segments_metadata = get_segments_with_bbox(
                path_to_pdf, poppler_path=None
            )

            # Store segment info for later use
            pdf_filename = os.path.basename(path_to_pdf)
            stored_segment_info[pdf_filename] = segments_metadata

        # Set up all_segments_dir path
        all_segments_dir = os.path.join(segment_directory, "all_segments")
        if os.path.exists(all_segments_dir):
            all_segments_dir_path = all_segments_dir
        else:
            all_segments_dir_path = None

        return {
            "segment_directory": segment_directory,
            "segments_existed": segments_already_exist,
            "all_segments_directory": all_segments_dir_path,
            "segments_info": segments_metadata,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error during segmentation: {str(e)}",
        )


def get_highlighted_segment_image(segment_id: str, pdf_filename: str) -> str:
    """
    Creates an image of the original PDF page with the segment highlighted

    Args:
        segment_id: ID of the segment to highlight (format: segment-{page}-{number})
        pdf_filename: Name of the PDF file

    Returns:
        str: Path to the created highlighted image
    """
    # Get the segment metadata
    segment_info = None

    # First try to find the segment in stored info
    if pdf_filename in stored_segment_info:
        for info in stored_segment_info[pdf_filename]:
            if info["segment_id"] == segment_id:
                segment_info = info
                break

    # If not found in stored info, try to extract details from segment_id
    if not segment_info:
        try:
            # Extract page and segment numbers from segment_id (format: segment-{page}-{number})
            parts = segment_id.split("-")
            if len(parts) >= 3:
                page_num = int(parts[1])
                segment_num = int(parts[2])

                # Create basic segment info
                segment_info = {
                    "segment_id": segment_id,
                    "pageNumber": page_num,
                    "segmentNumber": segment_num,
                    # Default bounding box that covers most of the page
                    "bbox": [50, 50, 800, 1100],
                }
            else:
                raise ValueError(f"Invalid segment_id format: {segment_id}")
        except (ValueError, IndexError) as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Could not parse segment_id: {segment_id}. Error: {str(e)}",
            )

    if not segment_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Segment metadata not found for segment: {segment_id}",
        )

    # Get the PDF file path
    pdf_path = os.path.join(PDF_DIR, pdf_filename)
    if not os.path.exists(pdf_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"PDF file not found: {pdf_filename}",
        )

    # Convert the specific page to image
    try:
        page_number = segment_info["pageNumber"]
        images = convert_from_path(pdf_path, 300)

        if page_number >= len(images):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Page {page_number} not found in PDF: {pdf_filename}",
            )

        page_image = np.array(images[page_number])

        # Draw a rectangle around the segment
        if "bbox" in segment_info:
            x0, y0, x1, y1 = segment_info["bbox"]
            cv2.rectangle(
                page_image,
                (x0, y0),
                (x1, y1),
                (0, 255, 0),  # Green color
                10,  # Line thickness
            )

            # Add a semi-transparent highlight over the segment
            overlay = page_image.copy()
            cv2.rectangle(
                overlay,
                (x0, y0),
                (x1, y1),
                (0, 255, 0),  # Green color
                -1,  # Fill rectangle
            )
            # Apply the overlay with transparency
            alpha = 0.3  # Transparency factor
            cv2.addWeighted(overlay, alpha, page_image, 1 - alpha, 0, page_image)

        # Create a filename for the highlighted image
        output_filename = f"highlighted_{segment_id}_{uuid.uuid4().hex[:8]}.png"
        output_path = os.path.join(SEGMENTS_DIR, output_filename)

        # Save the highlighted image
        cv2.imwrite(output_path, page_image)

        return output_path

    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating highlighted segment image: {str(e)}",
        )


# Keep other necessary functions intact
def segments_exist(filepath: str) -> Tuple[bool, Optional[str]]:
    """
    Check if segmented images already exist for the given PDF file.
    """
    # Validate input file
    if not filepath.lower().endswith(".pdf"):
        raise ValueError(f"Expected a PDF file, got: {filepath}")

    # Get the file stem
    file_path = Path(filepath)
    file_stem = file_path.stem

    # Look for directories in SEGMENTS_DIR that start with file_stem
    matching_dirs = [
        d
        for d in os.listdir(SEGMENTS_DIR)
        if d.startswith(file_stem) and os.path.isdir(os.path.join(SEGMENTS_DIR, d))
    ]

    if not matching_dirs:
        return False, None

    # Use the most recent directory
    base_directory = Path(os.path.join(SEGMENTS_DIR, matching_dirs[-1]))

    if not base_directory.exists() or not base_directory.is_dir():
        return False, None

    # Check if any segment directories exist
    segment_dirs = list(base_directory.glob("*_segments"))

    if not segment_dirs:
        # Also check for all_segments directory
        all_segments_dir = base_directory / "all_segments"
        if all_segments_dir.exists() and all_segments_dir.is_dir():
            # Check if there are segmented images in the all_segments directory
            segmented_images = list(all_segments_dir.glob("*_segmented.png"))
            if segmented_images:
                return True, str(base_directory)
        return False, None

    # Check if there are segment images in at least one directory
    for segment_dir in segment_dirs:
        if list(segment_dir.glob("*_segmented.png")):
            return True, str(base_directory)

    return False, None
