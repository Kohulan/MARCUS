import os
import uuid
import cv2
import numpy as np
import json
import hashlib
import threading
from typing import List, Optional, Tuple, Dict, Any
from pathlib import Path
from pdf2doi import pdf2doi
import fitz
from fastapi import HTTPException, status
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from decimer_segmentation import segment_chemical_structures
from app.config import PDF_DIR, SEGMENTS_DIR
from functools import lru_cache
import time
from contextlib import contextmanager
import multiprocessing as mp

# Thread-safe dictionary with lock for concurrent access
segment_info_lock = threading.Lock()
stored_segment_info = {}

# Cache for PDF metadata
pdf_cache_lock = threading.Lock()
pdf_metadata_cache = {}


# Performance monitoring decorator
def measure_performance(func):
    """Decorator to measure function execution time"""

    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        print(f"{func.__name__} took {end_time - start_time:.2f} seconds")
        return result

    return wrapper


@contextmanager
def thread_safe_dict_access(lock):
    """Context manager for thread-safe dictionary access"""
    lock.acquire()
    try:
        yield
    finally:
        lock.release()


@lru_cache(maxsize=128)
def get_doi_from_file(filepath: str) -> Dict[str, str]:
    """
    Extract the DOI from a PDF file with caching.

    Uses LRU cache to avoid repeated DOI extraction for the same files.
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


def get_pdf_hash(filepath: str) -> str:
    """Generate a hash of the PDF file for caching purposes"""
    hasher = hashlib.md5()
    with open(filepath, "rb") as f:
        # Read in chunks to handle large files efficiently
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def create_output_directory(filepath: str) -> str:
    """
    Create an output directory for storing segmented chemical structures.

    Optimized with better path handling and validation.
    """
    if not filepath.lower().endswith(".pdf"):
        raise ValueError(f"Expected a PDF file, got: {filepath}")

    file_path = Path(filepath)
    file_stem = file_path.stem
    output_dir_name = file_stem

    output_directory = Path(SEGMENTS_DIR) / output_dir_name

    # Fast check for existing directory
    if output_directory.exists():
        return str(output_directory)

    # Create directory with proper permissions
    output_directory.mkdir(mode=0o755, exist_ok=True)
    return str(output_directory)


def process_single_page(
    pdf_document, page_num: int, all_segments_dir: str, file_path: str
) -> List[Dict[str, Any]]:
    """
    Process a single PDF page for chemical structure segmentation.

    This function is designed to be called in parallel for better performance.
    """
    segments_metadata = []

    try:
        page = pdf_document[page_num]
        # Render page with 300 DPI (maintaining original quality)
        matrix = fitz.Matrix(300 / 72, 300 / 72)
        pix = page.get_pixmap(matrix=matrix, alpha=False)

        # Direct conversion to numpy array
        img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
            pix.h, pix.w, pix.n
        )

        # Free pixmap memory immediately
        pix = None

        # Segment chemical structures
        segments, bboxes = segment_chemical_structures(
            img_array, expand=True, return_bboxes=True
        )

        # Process segments
        for idx, segment in enumerate(segments):
            if segment.shape[0] == 0 or segment.shape[1] == 0:
                continue

            # Generate filename
            segment_filename = f"page_{page_num}_{idx}_segmented.png"
            segment_path = os.path.join(all_segments_dir, segment_filename)

            # Save the segment image (maintaining PNG format)
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
        print(f"Error processing page {page_num}: {str(e)}")
        # Don't raise, just log and continue with other pages

    return segments_metadata


@measure_performance
def get_segments_with_bbox(
    file_path: str, progress_callback=None
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Optimized segmentation with batch processing and parallel execution.
    """
    base_directory = create_output_directory(file_path)
    all_segments_dir = os.path.join(base_directory, "all_segments")
    os.makedirs(all_segments_dir, exist_ok=True)

    segments_metadata = []

    if file_path.lower().endswith(".pdf"):
        try:
            pdf_document = fitz.open(file_path)
            total_pages = pdf_document.page_count

            # Determine optimal batch size based on available memory
            available_memory = (
                os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
                if hasattr(os, "sysconf")
                else 4 * 1024 * 1024 * 1024
            )
            batch_size = min(
                4, max(1, available_memory // (1024 * 1024 * 1024))
            )  # 1GB per page estimate

            # Process pages in batches
            for batch_start in range(0, total_pages, batch_size):
                batch_end = min(batch_start + batch_size, total_pages)

                # Use ThreadPoolExecutor for I/O-bound operations
                with ThreadPoolExecutor(max_workers=min(4, batch_size)) as executor:
                    futures = []

                    for page_num in range(batch_start, batch_end):
                        future = executor.submit(
                            process_single_page,
                            pdf_document,
                            page_num,
                            all_segments_dir,
                            file_path,
                        )
                        futures.append((page_num, future))

                    # Collect results as they complete
                    for page_num, future in futures:
                        try:
                            page_segments = future.result(
                                timeout=30
                            )  # 30 second timeout per page
                            segments_metadata.extend(page_segments)

                            # Progress callback for API response
                            if progress_callback:
                                progress_callback(page_num + 1, total_pages)

                        except Exception as e:
                            print(f"Error processing page {page_num}: {str(e)}")
                            continue

                # Force garbage collection between batches
                import gc

                gc.collect()

            pdf_document.close()

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error converting PDF to images: {str(e)}",
            )
    else:
        # Single image processing
        try:
            img = cv2.imread(file_path, cv2.IMREAD_COLOR)
            segments, bboxes = segment_chemical_structures(
                img, expand=True, return_bboxes=True
            )

            for idx, segment in enumerate(segments):
                if segment.shape[0] == 0 or segment.shape[1] == 0:
                    continue

                segment_filename = f"page_0_{idx}_segmented.png"
                segment_path = os.path.join(all_segments_dir, segment_filename)
                cv2.imwrite(segment_path, segment)

                y0, x0, y1, x1 = bboxes[idx]

                segment_metadata = {
                    "segment_id": f"segment-0-{idx}",
                    "filename": segment_filename,
                    "path": os.path.join("all_segments", segment_filename),
                    "full_path": segment_path,
                    "pageNumber": 0,
                    "bbox": [int(x0), int(y0), int(x1), int(y1)],
                    "segmentNumber": idx + 1,
                    "pdfFilename": os.path.basename(file_path),
                }

                segments_metadata.append(segment_metadata)

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error segmenting image: {str(e)}",
            )

    # Save metadata efficiently
    save_segment_metadata(base_directory, segments_metadata)

    return base_directory, segments_metadata


def get_complete_segments(path_to_pdf: str, collect_all: bool = True) -> Dict[str, Any]:
    """
    Optimized complete pipeline with caching and early exit.
    """
    try:
        # Quick cache check using file hash
        pdf_hash = get_pdf_hash(path_to_pdf)

        with thread_safe_dict_access(pdf_cache_lock):
            if pdf_hash in pdf_metadata_cache:
                cached_result = pdf_metadata_cache[pdf_hash]
                # Verify cached files still exist
                if os.path.exists(cached_result["segment_directory"]):
                    return cached_result

        # Check if segments already exist
        segments_exist_result = segments_exist(path_to_pdf)
        segments_already_exist = segments_exist_result[0]
        existing_path = segments_exist_result[1]

        if segments_already_exist:
            segment_directory = existing_path
            pdf_filename = os.path.basename(path_to_pdf)

            # Try to get metadata from memory cache first
            with thread_safe_dict_access(segment_info_lock):
                segments_metadata = stored_segment_info.get(pdf_filename, [])

            # Load from file if not in memory
            if not segments_metadata:
                segments_metadata = load_segment_metadata(segment_directory)

                # Generate basic metadata if still not found
                if not segments_metadata:
                    all_segments_dir = os.path.join(segment_directory, "all_segments")
                    if os.path.exists(all_segments_dir):
                        segments_metadata = generate_basic_metadata(
                            all_segments_dir, pdf_filename
                        )

                # Update memory cache
                if segments_metadata:
                    with thread_safe_dict_access(segment_info_lock):
                        stored_segment_info[pdf_filename] = segments_metadata
        else:
            # Run segmentation
            segment_directory, segments_metadata = get_segments_with_bbox(path_to_pdf)

            # Update memory cache
            pdf_filename = os.path.basename(path_to_pdf)
            with thread_safe_dict_access(segment_info_lock):
                stored_segment_info[pdf_filename] = segments_metadata

        # Prepare result
        all_segments_dir = os.path.join(segment_directory, "all_segments")
        result = {
            "segment_directory": segment_directory,
            "segments_existed": segments_already_exist,
            "all_segments_directory": (
                all_segments_dir if os.path.exists(all_segments_dir) else None
            ),
            "segments_info": segments_metadata,
        }

        # Cache the result
        with thread_safe_dict_access(pdf_cache_lock):
            pdf_metadata_cache[pdf_hash] = result

        return result

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error during segmentation: {str(e)}",
        )


def generate_basic_metadata(
    all_segments_dir: str, pdf_filename: str
) -> List[Dict[str, Any]]:
    """Generate basic metadata from existing segment files"""
    segments_metadata = []

    for segment_file in sorted(os.listdir(all_segments_dir)):
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
                        "path": os.path.join("all_segments", segment_file),
                        "full_path": os.path.join(all_segments_dir, segment_file),
                        "pageNumber": page_num,
                        "segmentNumber": idx + 1,
                        "pdfFilename": pdf_filename,
                        "bbox": [0, 0, 1000, 1000],  # Default bbox
                    }

                    segments_metadata.append(segment_metadata)
                except ValueError:
                    continue

    return segments_metadata


@measure_performance
def get_highlighted_segment_image(segment_id: str, pdf_filename: str) -> str:
    """
    Optimized highlighted segment image generation with caching.
    """
    # Check cache first
    cache_key = f"{pdf_filename}_{segment_id}"
    cache_file = os.path.join(SEGMENTS_DIR, f"cache_highlighted_{cache_key}.png")

    if os.path.exists(cache_file):
        # Check if cache is still valid (within 1 hour)
        if time.time() - os.path.getmtime(cache_file) < 3600:
            return cache_file

    # Get segment metadata
    segment_info = None

    # Try memory cache first
    with thread_safe_dict_access(segment_info_lock):
        if pdf_filename in stored_segment_info:
            for info in stored_segment_info[pdf_filename]:
                if info["segment_id"] == segment_id:
                    segment_info = info
                    break

    # Load from file if not in memory
    if not segment_info:
        pdf_stem = Path(pdf_filename).stem
        matching_dirs = [
            d
            for d in os.listdir(SEGMENTS_DIR)
            if d.startswith(pdf_stem) and os.path.isdir(os.path.join(SEGMENTS_DIR, d))
        ]

        if matching_dirs:
            segment_dir = os.path.join(SEGMENTS_DIR, matching_dirs[-1])
            segments_metadata = load_segment_metadata(segment_dir)

            for info in segments_metadata:
                if info["segment_id"] == segment_id:
                    segment_info = info
                    with thread_safe_dict_access(segment_info_lock):
                        if pdf_filename not in stored_segment_info:
                            stored_segment_info[pdf_filename] = []
                        stored_segment_info[pdf_filename].append(info)
                    break

    # Generate basic info if not found
    if not segment_info:
        try:
            parts = segment_id.split("-")
            if len(parts) >= 3:
                page_num = int(parts[1])
                segment_num = int(parts[2])

                segment_info = {
                    "segment_id": segment_id,
                    "pageNumber": page_num,
                    "segmentNumber": segment_num,
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

    # Convert specific page to image
    try:
        page_number = segment_info["pageNumber"]

        # Use PyMuPDF for single page conversion (more efficient)
        pdf_document = fitz.open(pdf_path)

        if page_number >= pdf_document.page_count:
            pdf_document.close()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Page {page_number} not found in PDF: {pdf_filename}",
            )

        page = pdf_document[page_number]
        matrix = fitz.Matrix(300 / 72, 300 / 72)  # 300 DPI
        pix = page.get_pixmap(matrix=matrix, alpha=False)

        # Convert to numpy array
        page_image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
            pix.h, pix.w, pix.n
        )

        # Convert BGR to RGB for OpenCV
        if pix.n == 3:
            page_image = cv2.cvtColor(page_image, cv2.COLOR_RGB2BGR)

        pdf_document.close()
        pix = None

        # Draw rectangle and highlight
        if "bbox" in segment_info:
            x0, y0, x1, y1 = segment_info["bbox"]

            # Create overlay for transparency effect
            overlay = page_image.copy()
            cv2.rectangle(overlay, (x0, y0), (x1, y1), (0, 255, 0), -1)

            # Apply transparent overlay
            alpha = 0.3
            cv2.addWeighted(overlay, alpha, page_image, 1 - alpha, 0, page_image)

            # Draw border
            cv2.rectangle(page_image, (x0, y0), (x1, y1), (0, 255, 0), 10)

        # Save to cache file
        cv2.imwrite(cache_file, page_image)

        return cache_file

    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating highlighted segment image: {str(e)}",
        )


def segments_exist(filepath: str) -> Tuple[bool, Optional[str]]:
    """
    Optimized check for existing segments with caching.
    """
    if not filepath.lower().endswith(".pdf"):
        raise ValueError(f"Expected a PDF file, got: {filepath}")

    file_stem = Path(filepath).stem
    segments_base = Path(SEGMENTS_DIR)

    # Quick check with glob pattern
    matching_dirs = list(segments_base.glob(f"{file_stem}*"))
    matching_dirs = [d for d in matching_dirs if d.is_dir()]

    if not matching_dirs:
        return False, None

    # Use the most recent directory
    base_directory = max(matching_dirs, key=lambda d: d.stat().st_mtime)

    # Check for segments
    all_segments_dir = base_directory / "all_segments"
    if all_segments_dir.exists() and all_segments_dir.is_dir():
        # Quick check for any PNG files
        if any(all_segments_dir.glob("*_segmented.png")):
            return True, str(base_directory)

    # Check other segment directories
    segment_dirs = list(base_directory.glob("*_segments"))
    for segment_dir in segment_dirs:
        if any(segment_dir.glob("*_segmented.png")):
            return True, str(base_directory)

    return False, None


def save_segment_metadata(
    directory: str, segments_metadata: List[Dict[str, Any]]
) -> None:
    """
    Save segment metadata with atomic write operation.
    """
    try:
        metadata_file = os.path.join(directory, "segments_metadata.json")
        temp_file = metadata_file + ".tmp"

        # Create directory if needed
        os.makedirs(directory, exist_ok=True)

        # Write to temporary file first
        with open(temp_file, "w") as f:
            json.dump(segments_metadata, f, indent=2)

        # Atomic rename
        os.replace(temp_file, metadata_file)

        # Verify write
        if os.path.exists(metadata_file):
            file_size = os.path.getsize(metadata_file)
            print(f"Successfully saved metadata file ({file_size} bytes)")

    except Exception as e:
        print(f"Error saving segment metadata: {str(e)}")
        # Clean up temp file if it exists
        if os.path.exists(temp_file):
            os.remove(temp_file)


def load_segment_metadata(directory: str) -> List[Dict[str, Any]]:
    """
    Load segment metadata with error handling and caching.
    """
    metadata_file = os.path.join(directory, "segments_metadata.json")

    if os.path.exists(metadata_file):
        try:
            # Check file size to avoid loading huge files
            file_size = os.path.getsize(metadata_file)
            if file_size > 100 * 1024 * 1024:  # 100MB limit
                print(f"Warning: Metadata file too large ({file_size} bytes)")
                return []

            with open(metadata_file, "r") as f:
                data = json.load(f)
                print(f"Successfully loaded metadata ({len(data)} segments)")
                return data

        except json.JSONDecodeError as e:
            print(f"Warning: JSON decode error loading segment metadata: {str(e)}")
        except Exception as e:
            print(f"Warning: Failed to load segment metadata: {str(e)}")

    return []


# Cleanup function for API shutdown
def cleanup_caches():
    """Clean up caches and temporary files"""
    global stored_segment_info, pdf_metadata_cache

    with thread_safe_dict_access(segment_info_lock):
        stored_segment_info.clear()

    with thread_safe_dict_access(pdf_cache_lock):
        pdf_metadata_cache.clear()

    # Clean up old cache files
    cache_pattern = os.path.join(SEGMENTS_DIR, "cache_highlighted_*.png")
    import glob

    for cache_file in glob.glob(cache_pattern):
        try:
            if time.time() - os.path.getmtime(cache_file) > 3600:  # 1 hour old
                os.remove(cache_file)
        except:
            pass
