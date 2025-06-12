import os
import uuid
import cv2
import numpy as np
import json
from typing import List, Optional, Tuple, Dict, Any
from pathlib import Path
from pdf2doi import pdf2doi
import fitz
from fastapi import HTTPException, status
from concurrent.futures import ThreadPoolExecutor
from decimer_segmentation import segment_chemical_structures
from app.config import PDF_DIR, SEGMENTS_DIR

# Dictionary to store segment metadata from recently processed PDFs
stored_segment_info = {}


def get_doi_from_file(filepath: str) -> Dict[str, str]:
    """
    Extract the DOI (Digital Object Identifier) from a given PDF file.

    This function attempts to extract the DOI from the provided PDF file using the `pdf2doi` function.

    Args:
        filepath (str): Path to the PDF file from which to extract the DOI.

    Returns:
        Dict[str, str]: A dictionary with the key "doi" and the extracted DOI or fallback filename as the value.

    Raises:
        HTTPException: If an error occurs during DOI extraction, an HTTP 500 error is raised
                       with a description of the failure.
    """
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
    """
    Create an output directory for storing segmented chemical structures from a PDF file.

    This function generates a directory name based on the PDF filename and creates it within
    the configured segments directory. The directory is used to store all segmented chemical
    structures extracted from the PDF.

    Args:
        filepath (str): Path to the PDF file for which to create an output directory.

    Returns:
        str: Absolute path to the created or existing output directory.

    Raises:
        ValueError: If the input file is not a PDF file (doesn't end with .pdf extension).

    Example:
        >>> create_output_directory("/path/to/paper.pdf")
        "/segments/paper"
    """
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


def get_segments_with_bbox(file_path: str) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Run DECIMER segmentation on a PDF file and extract chemical structure segments with bounding boxes.

    This function processes a PDF file by converting it to images using PyMuPDF, then uses DECIMER
    segmentation to identify and extract chemical structures along with their bounding box coordinates.
    Each segment is saved as a separate image file with comprehensive metadata.

    Args:
        file_path (str): Path to the PDF file to be processed for segmentation.

    Returns:
        Tuple[str, List[Dict[str, Any]]]: A tuple containing:
            - str: Base directory path where segments are stored
            - List[Dict[str, Any]]: List of segment metadata dictionaries, each containing:
                - segment_id: Unique identifier for the segment
                - filename: Name of the saved segment image file
                - path: Relative path to the segment file
                - full_path: Absolute path to the segment file
                - pageNumber: Page number where segment was found
                - bbox: Bounding box coordinates [x0, y0, x1, y1]
                - segmentNumber: Sequential number of segment on the page
                - pdfFilename: Original PDF filename

    Raises:
        HTTPException: If an error occurs during:
            - PDF to image conversion (status 500)
            - Chemical structure segmentation (status 500)

    Example:
        >>> base_dir, segments = get_segments_with_bbox("/path/to/paper.pdf")
        >>> print(f"Found {len(segments)} chemical structures in {base_dir}")
        Found 5 chemical structures in /segments/paper
    """
    # Convert PDF to images using PyMuPDF
    if file_path.lower().endswith(".pdf"):
        try:
            pdf_document = fitz.open(file_path)
            images = []
            # Pre-allocate list for known size
            images = [None] * pdf_document.page_count

            # Use thread pool for parallel page rendering
            def render_page(page_num):
                page = pdf_document[page_num]
                # Render page to image with 300 DPI
                matrix = fitz.Matrix(300 / 72, 300 / 72)
                pix = page.get_pixmap(matrix=matrix, alpha=False)  # Skip alpha channel
                # Direct conversion to numpy array
                img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                    pix.h, pix.w, pix.n
                )
                return page_num, img_array

            # Use thread pool for I/O bound operations
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = [
                    executor.submit(render_page, i)
                    for i in range(pdf_document.page_count)
                ]
                for future in futures:
                    page_num, img_array = future.result()
                    images[page_num] = img_array

            pdf_document.close()
            # Filter out any None values
            images = [img for img in images if img is not None]

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error converting PDF to images: {str(e)}",
            )
    else:
        # Use faster image reading with proper flags
        images = [cv2.imread(file_path, cv2.IMREAD_COLOR)]

    # Create output directory
    base_directory = create_output_directory(file_path)
    all_segments_dir = os.path.join(base_directory, "all_segments")
    os.makedirs(all_segments_dir, exist_ok=True)

    # Process each page
    segments_metadata = []
    for page_num, page_img in enumerate(images):
        try:
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

    # Save segment metadata to a file for later use
    save_segment_metadata(base_directory, segments_metadata)

    return base_directory, segments_metadata


def get_complete_segments(path_to_pdf: str, collect_all: bool = True) -> Dict[str, Any]:
    """
    Complete pipeline for PDF processing including segmentation, metadata extraction, and organization.

    This function provides a comprehensive workflow for processing PDF files containing chemical
    structures. It handles both new segmentation and retrieval of existing segments, maintains
    metadata consistency, and organizes all segments in a structured directory format.

    Args:
        path_to_pdf (str): Absolute or relative path to a PDF file to be processed.
        collect_all (bool, optional): Whether to copy all segments to a common directory for
                                     easy access. Defaults to True.

    Returns:
        Dict[str, Any]: A comprehensive dictionary containing:
            - segment_directory (str): Path to the main directory containing all segments
            - segments_existed (bool): Whether segments already existed before this call
            - all_segments_directory (Optional[str]): Path to the common segments directory
            - segments_info (List[Dict[str, Any]]): Detailed metadata for each segment including:
                - segment_id: Unique identifier
                - filename: Segment image filename
                - path: Relative path to segment
                - full_path: Absolute path to segment
                - pageNumber: Source page number
                - bbox: Bounding box coordinates
                - segmentNumber: Sequential segment number
                - pdfFilename: Original PDF name

    Raises:
        HTTPException: If an error occurs during:
            - PDF validation or reading (status 500)
            - Segmentation processing (status 500)
            - Directory creation or file operations (status 500)

    Example:
        >>> result = get_complete_segments("/path/to/chemistry_paper.pdf")
        >>> print(f"Found {len(result['segments_info'])} segments")
        >>> print(f"Segments directory: {result['segment_directory']}")
        Found 8 segments
        Segments directory: /segments/chemistry_paper
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

            # If we don't have metadata stored, try to load from the metadata file first
            if not segments_metadata:
                segments_metadata = load_segment_metadata(segment_directory)

                # If still no metadata, create basic entries
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

                # Store the loaded/created metadata in the in-memory cache
                if segments_metadata:
                    stored_segment_info[pdf_filename] = segments_metadata
        else:
            # Run the segmentation with bounding box collection
            segment_directory, segments_metadata = get_segments_with_bbox(path_to_pdf)

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
    Create a highlighted image showing the location of a specific chemical segment within its original PDF page.

    This function generates a visual representation of where a chemical structure segment was
    found by overlaying a highlighted bounding box on the original PDF page. The resulting
    image helps users understand the context and location of extracted chemical structures.

    Args:
        segment_id (str): Unique identifier of the segment to highlight. Expected format:
                         "segment-{page_number}-{segment_index}" (e.g., "segment-0-1").
        pdf_filename (str): Name of the original PDF file containing the segment.

    Returns:
        str: Absolute path to the generated highlighted image file. The image shows the
             original PDF page with a green rectangle and semi-transparent overlay
             highlighting the segment location.

    Raises:
        HTTPException: With appropriate status codes for various error conditions:
            - 400: Invalid segment_id format that cannot be parsed
            - 404: Segment metadata not found, PDF file not found, or page not found
            - 500: Error during image processing, PDF conversion, or file operations

    Example:
        >>> image_path = get_highlighted_segment_image("segment-0-1", "chemistry_paper.pdf")
        >>> print(f"Highlighted image saved to: {image_path}")
        Highlighted image saved to: /segments/highlighted_segment-0-1_a1b2c3d4.png

    Note:
        - The function uses a green rectangle with 10px thickness for the border
        - A semi-transparent green overlay (30% opacity) fills the segment area
        - Generated images are saved in the SEGMENTS_DIR with unique filenames
        - If bounding box information is missing, a default bbox covering most of the page is used
    """
    # Get the segment metadata
    segment_info = None

    # First try to find the segment in stored info
    if pdf_filename in stored_segment_info:
        for info in stored_segment_info[pdf_filename]:
            if info["segment_id"] == segment_id:
                segment_info = info
                break

    # If not found in stored info, try to load from metadata file
    if not segment_info:
        # Try to find the segment directory based on the PDF filename
        pdf_stem = Path(pdf_filename).stem
        matching_dirs = [
            d
            for d in os.listdir(SEGMENTS_DIR)
            if d.startswith(pdf_stem) and os.path.isdir(os.path.join(SEGMENTS_DIR, d))
        ]

        if matching_dirs:
            # Use the most recent directory
            segment_dir = os.path.join(SEGMENTS_DIR, matching_dirs[-1])
            # Load metadata from file
            segments_metadata = load_segment_metadata(segment_dir)

            # Look for the segment in the loaded metadata
            for info in segments_metadata:
                if info["segment_id"] == segment_id:
                    segment_info = info
                    # Update in-memory cache
                    if not pdf_filename in stored_segment_info:
                        stored_segment_info[pdf_filename] = []
                    stored_segment_info[pdf_filename].append(info)
                    break

    # If still not found, try to extract details from segment_id
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
    Check if segmented chemical structure images already exist for a given PDF file.

    This function determines whether chemical structure segmentation has already been
    performed on the specified PDF file by looking for existing segment directories
    and segment image files in the configured segments directory.

    Args:
        filepath (str): Path to the PDF file to check for existing segments.

    Returns:
        Tuple[bool, Optional[str]]: A tuple containing:
            - bool: True if segments exist, False otherwise
            - Optional[str]: Path to the existing segments directory if found, None otherwise

    Raises:
        ValueError: If the input file is not a PDF file (doesn't end with .pdf extension).

    Example:
        >>> exists, path = segments_exist("/path/to/chemistry_paper.pdf")
        >>> if exists:
        ...     print(f"Segments found in: {path}")
        ... else:
        ...     print("No existing segments found")
        Segments found in: /segments/chemistry_paper

    Note:
        - The function looks for directories that start with the PDF filename stem
        - It checks for both individual segment directories and an "all_segments" directory
        - If multiple matching directories exist, it returns the most recent one
        - Segment files must follow the naming pattern "*_segmented.png"
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


def save_segment_metadata(
    directory: str, segments_metadata: List[Dict[str, Any]]
) -> None:
    """
    Save chemical structure segment metadata to a JSON file for persistent storage.

    This function serializes segment metadata to a JSON file within the specified directory,
    enabling persistent storage and retrieval of segment information across application
    sessions. The metadata includes details about segment locations, bounding boxes, and
    file paths.

    Args:
        directory (str): Target directory where the metadata JSON file will be saved.
                        The file will be named "segments_metadata.json".
        segments_metadata (List[Dict[str, Any]]): List of segment metadata dictionaries
                                                 containing information such as:
                                                 - segment_id: Unique identifier
                                                 - filename: Segment image filename
                                                 - bbox: Bounding box coordinates
                                                 - pageNumber: Source page number
                                                 - And other segment properties

    Returns:
        None

    Raises:
        Exception: Various file system errors may occur during directory creation or
                  file writing operations. Error details are printed to console for
                  debugging purposes.

    Example:
        >>> metadata = [{"segment_id": "segment-0-1", "filename": "page_0_1_segmented.png", ...}]
        >>> save_segment_metadata("/segments/chemistry_paper", metadata)
        Saving metadata to: /segments/chemistry_paper/segments_metadata.json
        Successfully saved metadata file (1245 bytes)

    Note:
        - Creates the target directory if it doesn't exist
        - Overwrites existing metadata files
        - JSON is formatted with 2-space indentation for readability
        - Includes debugging output for troubleshooting file operations
    """
    try:
        metadata_file = os.path.join(directory, "segments_metadata.json")
        print(f"Saving metadata to: {metadata_file}")
        if not os.path.exists(directory):
            print(f"Warning: Directory does not exist: {directory}")
            os.makedirs(directory, exist_ok=True)
            print(f"Created directory: {directory}")

        with open(metadata_file, "w") as f:
            json.dump(segments_metadata, f, indent=2)

        # Verify the file was created
        if os.path.exists(metadata_file):
            file_size = os.path.getsize(metadata_file)
            print(f"Successfully saved metadata file ({file_size} bytes)")
        else:
            print(f"Error: Metadata file not found after saving: {metadata_file}")
    except Exception as e:
        print(f"Error saving segment metadata: {str(e)}")
        # Print more debugging information
        print(f"Directory exists: {os.path.exists(directory)}")
        print(f"Directory is writable: {os.access(directory, os.W_OK)}")
        print(f"Segments metadata count: {len(segments_metadata)}")


def load_segment_metadata(directory: str) -> List[Dict[str, Any]]:
    """
    Load chemical structure segment metadata from a JSON file in the segments directory.

    This function retrieves previously saved segment metadata from a JSON file, enabling
    the restoration of segment information across application sessions. It handles various
    error conditions gracefully and provides detailed debugging information.

    Args:
        directory (str): Directory containing the metadata JSON file. The function looks
                        for a file named "segments_metadata.json" in this directory.

    Returns:
        List[Dict[str, Any]]: List of segment metadata dictionaries. Each dictionary
                             contains segment information such as:
                             - segment_id: Unique identifier for the segment
                             - filename: Name of the segment image file
                             - bbox: Bounding box coordinates [x0, y0, x1, y1]
                             - pageNumber: Source page number
                             - segmentNumber: Sequential segment number
                             - And other segment properties
                             Returns an empty list if the file doesn't exist or cannot be read.

    Returns:
        List[Dict[str, Any]]: Empty list if metadata file is not found or cannot be parsed.

    Example:
        >>> metadata = load_segment_metadata("/segments/chemistry_paper")
        >>> if metadata:
        ...     print(f"Loaded {len(metadata)} segments")
        ...     for segment in metadata:
        ...         print(f"Segment: {segment['segment_id']}")
        Attempting to load metadata from: /segments/chemistry_paper/segments_metadata.json
        Successfully loaded metadata (5 segments)
        Loaded 5 segments

    Note:
        - Returns empty list if metadata file doesn't exist (not an error condition)
        - Handles JSON parsing errors gracefully with detailed error reporting
        - Provides debugging output including file size and content preview on errors
        - Does not raise exceptions - designed to be fault-tolerant
    """
    metadata_file = os.path.join(directory, "segments_metadata.json")
    print(f"Attempting to load metadata from: {metadata_file}")

    if os.path.exists(metadata_file):
        try:
            with open(metadata_file, "r") as f:
                data = json.load(f)
                print(f"Successfully loaded metadata ({len(data)} segments)")
                return data
        except json.JSONDecodeError as e:
            print(f"Warning: JSON decode error loading segment metadata: {str(e)}")
            print(f"File size: {os.path.getsize(metadata_file)} bytes")
            # Try to read the raw content for debugging
            try:
                with open(metadata_file, "r") as f:
                    content = f.read(100)  # Read first 100 chars
                    print(f"File content starts with: {content}...")
            except Exception as read_err:
                print(f"Could not read file content: {str(read_err)}")
        except Exception as e:
            print(f"Warning: Failed to load segment metadata: {str(e)}")
    else:
        print(f"Metadata file not found: {metadata_file}")

    return []
