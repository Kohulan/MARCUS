import os
import re

from fastapi import HTTPException, status, File, Form, UploadFile
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import (
    DocumentConverter,
    PdfFormatOption,
    ConversionResult,
)
from PyPDF2 import PdfReader, PdfWriter
from app.config import PDF_DIR

artifacts_path = "/Users/kohulanrajan/.cache/docling/models"

pipeline_options = PdfPipelineOptions(artifacts_path=artifacts_path)
doc_converter = DocumentConverter(
    format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
)


def _is_author_line(content: str) -> bool:
    """Simple check for author/affiliation information."""
    if len(content.strip()) < 3:
        return False
    
    content_lower = content.lower()
    
    # Key indicators for author/affiliation content
    indicators = [
        "@", "university", "universita", "institute", "department", 
        "correspondence:", "received:", "tel:", "fax:", "email:", 
        "dipartimento", "via ", "italy", "hospital", "center",
        "†", "‡", "§", "*", "orcid", "laboratory", "college",
        "table ", "figure ", "compounds 1", "anti-inflammatory activity"
    ]
    
    # Check for multiple capitalized names (likely authors)
    words = content.split()
    if len(words) >= 3 and len(content) < 200:
        cap_words = [w for w in words[:5] if len(w) > 1 and w[0].isupper()]
        if len(cap_words) >= 3:
            return True
    
    return any(indicator in content_lower for indicator in indicators)


def extract_first_three_pages(input_pdf_path, number_of_pages=2):
    """
    Extract a specified number of pages from the beginning of a PDF file.

    Creates a new PDF file containing only the first N pages from the input PDF,
    useful for processing large documents where only the initial pages are needed.

    Args:
        input_pdf_path (str): Path to the source PDF file to extract pages from.
        number_of_pages (int, optional): Number of pages to extract from the beginning. Defaults to 2.

    Returns:
        str: Path to the newly created PDF file containing the extracted pages.
             The output file has "_out" appended before the file extension.

    Raises:
        FileNotFoundError: If the input PDF file does not exist.
        Exception: If PDF reading/writing operations fail.

    Example:
        >>> output_path = extract_first_three_pages("document.pdf", 2)
        >>> print(output_path)
        "document_out.pdf"
    """
    # Open the original PDF
    with open(input_pdf_path, "rb") as input_pdf_file:
        pdf_reader = PdfReader(input_pdf_file)
        pdf_writer = PdfWriter()

        # Determine the number of pages to extract
        num_pages = min(number_of_pages, len(pdf_reader.pages))

        # Add the pages to the writer object
        for page_num in range(num_pages):
            page = pdf_reader.pages[page_num]
            pdf_writer.add_page(page)

        # Construct the output file path
        base_name = os.path.splitext(input_pdf_path)[0]
        output_pdf_file_path = f"{base_name}_out.pdf"

        # Write the pages to a new PDF
        with open(output_pdf_file_path, "wb") as output_pdf_file:
            pdf_writer.write(output_pdf_file)
        print(output_pdf_file_path)
        return output_pdf_file_path


def get_converted_document(path, number_of_pages=2):
    """
    Convert a PDF document to structured JSON format using Docling.

    Extracts the first N pages from a PDF and converts them to a structured
    document format that can be processed for content extraction.

    Args:
        path (str): Path to the PDF file to be converted.
        number_of_pages (int, optional): Number of pages to process. Defaults to 2.

    Returns:
        dict: Document structure in JSON format containing text elements,
              layout information, and metadata from the converted PDF.

    Raises:
        Exception: If document conversion fails or file cannot be processed.

    Example:
        >>> doc_dict = get_converted_document("paper.pdf", 2)
        >>> print(doc_dict.keys())
        dict_keys(['texts', 'schema_name', 'name', ...])
    """
    output_pdf_file_path = extract_first_three_pages(path, number_of_pages)
    converter = DocumentConverter()
    conv_result: ConversionResult = converter.convert(output_pdf_file_path)
    conv_result_dict = conv_result.document.export_to_dict()
    return conv_result_dict


def extract_paper_content(doc_json):
    """
    Extract paper content from Docling format JSON with optimized performance.

    Processes structured document JSON to extract title, abstract, and main text
    while filtering out author information, affiliations, and other metadata.

    Args:
        doc_json (dict): The structured document JSON from Docling conversion.

    Returns:
        dict: Dictionary containing extracted content with keys:
              - title: Paper title text
              - abstract: Abstract section content
              - main_text: Main body text content

    Example:
        >>> content = extract_paper_content(docling_json)
        >>> print(content['title'])
        "Chemical Structure Analysis Methods"
    """
    # Pre-compile patterns for speed
    section_keywords = {"ABSTRACT", "INTRODUCTION", "EXPERIMENTAL", "METHODS", "RESULTS"}
    intro_keywords = {"INTRODUCTION", "METHODOLOGY", "MATERIALS", "EXPERIMENTAL"}
    stop_keywords = {"RESULTS", "REFERENCES", "BIBLIOGRAPHY", "ACKNOWLEDGMENT"}
    metadata_indicators = {"correspondence:", "received:", "funding:", "doi:", "copyright"}
    
    texts = doc_json.get("texts", [])
    if not texts:
        return {"title": "", "abstract": "", "main_text": ""}
    
    # Single pass processing with state tracking
    title = ""
    abstract_parts = []
    main_text_parts = []
    
    # State variables
    collecting_abstract = False
    found_intro = False
    abstract_found = False
    
    for text in texts:
        content = text.get("text", "").strip()
        if not content:
            continue
            
        # APPLY OPTIMIZED AUTHOR FILTERING HERE
        if _is_author_line(content):
            continue
            
        # Pre-compute expensive operations once
        content_upper = content.upper()
        content_lower = content.lower()
        label = text.get("label", "")
        is_header = label == "section_header"
        page_no = text.get("prov", [{}])[0].get("page_no", 1) if text.get("prov") else 1
        
        # Skip page headers/footers early
        if label in ["page_header", "page_footer"]:
            continue
            
        # Skip metadata content early
        if any(indicator in content_lower for indicator in metadata_indicators):
            continue
            
        # Title extraction (only if not found yet)
        if not title and is_header:
            if text.get("level") == 1 and "RESULTS" not in content_upper and len(content) > 5:
                title = content
            elif len(content) > 20 and not any(kw in content_upper for kw in section_keywords):
                title = content
                
        # Abstract processing
        if not abstract_found:
            if is_header and content_upper == "ABSTRACT":
                collecting_abstract = True
                abstract_found = True
                continue
            elif "ABSTRACT:" in content_upper:
                abstract_parts.append(content.replace("ABSTRACT:", "").replace("Abstract:", "").strip())
                collecting_abstract = True
                abstract_found = True
                continue
                
        if collecting_abstract and not any(kw in content_upper for kw in section_keywords):
            abstract_parts.append(content)
        elif collecting_abstract and is_header:
            collecting_abstract = False
            
        # Main text processing
        if is_header and any(kw in content_upper for kw in intro_keywords):
            found_intro = True
            main_text_parts.append(content)
        elif found_intro and is_header and any(kw in content_upper for kw in stop_keywords):
            break
        elif found_intro and page_no <= 6:
            main_text_parts.append(content)
            
    # Fallback for missing content (simplified single pass)
    if not abstract_parts and not main_text_parts:
        for text in texts[:50]:  # Limit to first 50 elements for speed
            content = text.get("text", "").strip()
            if (len(content) >= 5 and 
                text.get("label") not in ["page_header", "page_footer"] and
                text.get("prov", [{}])[0].get("page_no", 1) <= 3 and
                not _is_author_line(content)):  # APPLY OPTIMIZED FILTERING HERE TOO
                main_text_parts.append(content)
    
    return {
        "title": title,
        "abstract": " ".join(abstract_parts),
        "main_text": " ".join(main_text_parts)
    }


def extract_from_docling_document(data):
    """
    Extract paper content from a Docling document format.

    Processes a structured Docling document to extract key academic paper components
    including title, abstract, and main text content.

    Args:
        data (dict): The Docling document JSON containing structured document data.

    Returns:
        dict: Dictionary containing extracted content with keys:
              - title: Paper title text
              - abstract: Abstract content
              - main_text: Main body text
              Or error message if format is invalid.

    Example:
        >>> content = extract_from_docling_document(docling_json)
        >>> print(content['title'])
        "A Novel Approach to Chemical Structure Recognition"
    """
    # For Docling format, we need to extract the main document structure
    if "schema_name" in data and data["schema_name"] == "DoclingDocument":
        result = extract_paper_content(data)

        # Check if any of the key components are empty and extract additional info if needed
        if (
            not result.get("title")
            or not result.get("abstract")
            or not result.get("main_text")
        ):
            # Try to extract more text based on document structure
            texts = data.get("texts", [])

            # If title is empty, try to find a likely title
            if not result.get("title"):
                for text in texts:
                    content = text.get("text", "").strip()
                    # Look for section headers that could be titles (longer than typical headers)
                    if (
                        text.get("label") == "section_header"
                        and len(content) > 30
                        and not any(
                            keyword in content.upper()
                            for keyword in [
                                "ABSTRACT",
                                "INTRODUCTION",
                                "RESULTS",
                                "METHODS",
                                "EXPERIMENTAL",
                            ]
                        )
                    ):
                        result["title"] = content
                        break
                    # Look for large font text at the beginning
                    elif (
                        text.get("label") == "paragraph"
                        and text.get("page_number") == 1
                        and text.get("font_size", 0) > 12
                    ):
                        result["title"] = content
                        break

            # If abstract is still empty, use a more comprehensive approach
            if not result.get("abstract"):
                # Try to find abstract section by looking for structured content
                abstract_texts = []
                for i, text in enumerate(texts):
                    content = text.get("text", "").strip()

                    # Look for abstract-related content
                    if any(
                        keyword in content.lower()
                        for keyword in [
                            "introduction:",
                            "objective:",
                            "methodology:",
                            "results:",
                            "conclusion:",
                        ]
                    ):
                        abstract_texts.append(content)

                    # If we find "introduction" header, stop collecting
                    if (
                        text.get("label") == "section_header"
                        and "introduction" in content.lower()
                    ):
                        break

                if abstract_texts:
                    result["abstract"] = " ".join(abstract_texts)

        return result
    else:
        return {"error": "Not a valid Docling document format"}


def combine_to_paragraph(result_dict):
    """
    Combine extracted paper components into a single formatted paragraph.

    Merges title, abstract, and main text from paper extraction results into
    a clean, properly formatted single paragraph with normalized spacing.

    Args:
        result_dict (dict): Dictionary containing 'title', 'abstract', and 'main_text' keys.

    Returns:
        str: Single paragraph containing all paper content with cleaned formatting.
             Returns error message if input is invalid.

    Example:
        >>> content = {"title": "Paper Title", "abstract": "Abstract text", "main_text": "Body text"}
        >>> paragraph = combine_to_paragraph(content)
        >>> print(len(paragraph.split()))
        150
    """
    # Check for valid input
    if not isinstance(result_dict, dict):
        return "Error: Input must be a dictionary."

    # Extract components
    title = result_dict.get("title", "").strip()
    abstract = result_dict.get("abstract", "").strip()
    main_text = result_dict.get("main_text", "").strip()

    # Combine components with appropriate spacing
    combined_text = []

    if title:
        combined_text.append(title)

    if abstract:
        combined_text.append(abstract)

    if main_text:
        combined_text.append(main_text)

    # Join with spaces and clean up formatting
    combined_paragraph = " ".join(combined_text)

    # Clean up the text formatting
    # Replace newlines with spaces
    combined_paragraph = combined_paragraph.replace("\n", " ")
    # Replace multiple spaces with single spaces
    combined_paragraph = re.sub(r"\s+", " ", combined_paragraph)
    # Fix spacing around punctuation
    combined_paragraph = re.sub(r"\s+([.,;:?!])", r"\1", combined_paragraph)
    # Remove extra spaces around common symbols
    combined_paragraph = re.sub(r"\s*\|\s*", " | ", combined_paragraph)
    combined_paragraph = re.sub(r"\s*~\s*", " ", combined_paragraph)
    # Clean up common formatting issues
    combined_paragraph = re.sub(r"([a-z])([A-Z])", r"\1 \2", combined_paragraph)
    # Remove unnecessary symbols that might have been OCR artifacts
    combined_paragraph = re.sub(r"[ŒœŸÿ]", "", combined_paragraph)
    # Fix common word breaks
    combined_paragraph = re.sub(r"(\w)-\s+(\w)", r"\1\2", combined_paragraph)

    # Final cleanup - ensure single spaces
    combined_paragraph = re.sub(r"\s+", " ", combined_paragraph).strip()

    return combined_paragraph


async def extract_pdf_text(
    pdf_file: UploadFile = File(...),
    pages: int = Form(2, description="Number of pages to process"),
):
    """
    Extract and process text content from an uploaded PDF file.

    Handles PDF upload, converts to structured format, extracts paper content,
    and returns combined text. Falls back to full page extraction if content is insufficient.

    Args:
        pdf_file (UploadFile): The PDF file to process (required).
        pages (int): Number of pages to process from the beginning. Defaults to 2.

    Returns:
        dict: JSON object containing:
              - text: Combined extracted text content
              - pdf_filename: Sanitized filename of the processed PDF

    Raises:
        HTTPException:
            - 400: If uploaded file is not a PDF
            - 500: If PDF processing fails

    Example:
        >>> result = await extract_pdf_text(pdf_file, pages=2)
        >>> print(result['text'][:100])
        "Title: Novel Chemical Analysis Abstract: This paper presents..."
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
        if len(combined_text.split()) <= 10:
            # If extracted text has 10 or fewer words, extract the whole first page
            all_text = extract_full_page_text(json_data)
            if all_text:
                combined_text = all_text

        # Additional check: if combined text is still too short or doesn't contain substantial content
        elif (
            len(combined_text.split()) < 100
            or "introduction" not in combined_text.lower()
            or "phytochemical analysis" in combined_text.lower()
        ):
            # Try a more aggressive extraction approach for structured papers
            enhanced_text = extract_enhanced_paper_content(json_data)
            if enhanced_text and len(enhanced_text.split()) > len(
                combined_text.split()
            ):
                combined_text = enhanced_text

        return {"text": combined_text, "pdf_filename": safe_filename}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing PDF: {str(e)}",
        )


def extract_enhanced_paper_content(doc_json):
    """
    Enhanced extraction for papers with structured content like the example provided.

    This function handles cases where papers have structured abstracts with
    subsections like Introduction, Objective, Methodology, Results, Conclusion.

    Args:
        doc_json (dict): The JSON representation of the document

    Returns:
        str: Enhanced extracted text content or empty string if extraction fails
    """
    texts = doc_json.get("texts", [])
    extracted_content = []

    # Look for title - longest section header that's not a common section
    title = ""
    for text in texts:
        if text.get("label") == "section_header":
            content = text.get("text", "").strip()
            if len(content) > 20 and not any(  # Reduced from 30 to 20
                keyword in content.upper()
                for keyword in [
                    "ABSTRACT",
                    "INTRODUCTION",
                    "EXPERIMENTAL",
                    "METHODS",
                    "RESULTS",
                ]
            ):
                title = content
                break

    if title:
        extracted_content.append(title)

    # Extract structured abstract content (Introduction, Objective, etc.)
    abstract_content = []
    introduction_content = []
    main_content = []
    capturing_abstract = False
    capturing_introduction = False
    capturing_main = False

    for i, text in enumerate(texts):
        content = text.get("text", "").strip()
        page_no = text.get("prov", [{}])[0].get("page_no", 1) if text.get("prov") else 1

        # Skip empty content and headers/footers, but be more lenient
        if (
            not content
            or text.get("label") in ["page_header", "page_footer"]
            or len(content) < 3  # Reduced from 5 to 3
        ):
            continue

        # Check for abstract section
        if text.get("label") == "section_header" and content.upper() == "ABSTRACT":
            capturing_abstract = True
            continue

        # Check for structured abstract content (Introduction:, Objective:, etc.)
        if capturing_abstract and any(
            keyword in content
            for keyword in [
                "Introduction:",
                "Objective:",
                "Methodology:",
                "Results:",
                "Conclusion:",
                "Background:",
                "Methods:",
                "Purpose:",
                "Aim:",
                "Summary:",
            ]
        ):
            abstract_content.append(content)
            continue

        # Check for main introduction section
        if text.get("label") == "section_header" and (
            "INTRODUCTION" in content.upper()
            or ("|" in content and "INTRODUCTION" in content.upper())
        ):
            capturing_abstract = False  # Stop capturing abstract
            capturing_introduction = True
            continue

        # Check for main content sections
        if text.get("label") == "section_header" and any(
            section in content.upper()
            for section in [
                "METHODS",
                "METHODOLOGY",
                "MATERIALS",
                "EXPERIMENTAL",
                "DISCUSSION",
                "ANALYSIS",
            ]
        ):
            capturing_introduction = False
            capturing_main = True
            continue

        # Stop main capture at results or references
        if capturing_main and text.get("label") == "section_header":
            if any(
                section in content.upper()
                for section in [
                    "RESULTS",
                    "REFERENCES",
                    "BIBLIOGRAPHY",
                    "ACKNOWLEDGMENT",
                ]
            ):
                capturing_main = False

        # Capture abstract content with simple filtering
        if capturing_abstract and page_no <= 3:
            if not _is_author_line(content):
                abstract_content.append(content)

        # Capture introduction content (more pages but with comprehensive filtering)
        if capturing_introduction and page_no <= 5:  # Increased from 3 to 5
            # Filter out author information and unwanted content
            if (
                not any(
                    indicator in content.lower()
                    for indicator in [
                        "correspondence:",
                        "received:",
                        "funding:",
                        "doi:",
                        "copyright",
                        "@",  # Email addresses
                        "university",
                        "institute",
                        "department",
                        "college",
                        "school of",
                        "faculty of",
                        "laboratory",
                        "lab ",
                        "center for",
                        "centre for",
                        "hospital",
                        "medical center",
                        "research center",
                        "orcid",
                        "author",
                        "affiliation",
                    ]
                )
                and not _is_author_line(content)
               
            ):
                introduction_content.append(content)

        # Capture main content with comprehensive filtering
        if capturing_main and page_no <= 6:
            # Filter out author information and unwanted content
            if (
                not any(
                    indicator in content.lower()
                    for indicator in [
                        "correspondence:",
                        "received:",
                        "funding:",
                        "doi:",
                        "copyright",
                        "@",  # Email addresses
                        "university",
                        "institute",
                        "department",
                        "college",
                        "school of",
                        "faculty of",
                        "laboratory",
                        "lab ",
                        "center for",
                        "centre for",
                        "hospital",
                        "medical center",
                        "research center",
                        "orcid",
                        "author",
                        "affiliation",
                    ]
                )
                and not _is_author_line(content)
               
            ):
                main_content.append(content)

    # Combine all content
    if title:
        extracted_content.append(title)
    if abstract_content:
        extracted_content.extend(abstract_content)
    if introduction_content:
        extracted_content.extend(introduction_content)
    if main_content:
        extracted_content.extend(
            main_content[:8]
        )  # Limit main content to avoid too much

    # Remove duplicate title if it appears again in the content
    if title and len(extracted_content) > 1:
        # Check if title appears as duplicate in the content
        title_words = set(title.lower().split())
        filtered_content = [title]  # Keep the original title

        for content_piece in extracted_content[1:]:  # Skip the first title
            content_words = set(content_piece.lower().split())
            # If more than 70% of words match the title, skip it
            if len(title_words & content_words) / max(len(title_words), 1) < 0.7:
                filtered_content.append(content_piece)

        extracted_content = filtered_content

    # Enhanced fallback with more comprehensive extraction
    if len(extracted_content) < 5:  # Increased threshold from 3 to 5
        extracted_content = []
        if title:
            extracted_content.append(title)

        for text in texts:
            content = text.get("text", "").strip()
            page_no = (
                text.get("prov", [{}])[0].get("page_no", 1) if text.get("prov") else 1
            )

            # Process first 4 pages instead of 2
            if page_no > 4:
                continue

            # Skip empty content and headers/footers, but be more lenient
            if (
                not content
                or text.get("label") in ["page_header", "page_footer"]
                or len(content) < 5  # Reduced from 10 to 5
            ):
                continue

            # Enhanced filtering - skip author info, metadata, and unwanted content
            if (
                any(
                    indicator in content.lower()
                    for indicator in [
                        "correspondence:",
                        "received:",
                        "funding:",
                        "doi:",
                        "copyright",
                        "journal of",
                        "volume",
                        "issue",
                        "@",  # Email addresses
                        "university",
                        "institute",
                        "department",
                        "college",
                        "school of",
                        "faculty of",
                        "laboratory",
                        "lab ",
                        "center for",
                        "centre for",
                        "hospital",
                        "medical center",
                        "research center",
                        "orcid",
                        "author",
                        "affiliation",
                    ]
                )
                or _is_author_line(content)
               
            ):
                continue

            # Skip if it's just page numbers or obvious journal info
            if content.isdigit() or (
                len(content) < 50
                and any(
                    journal in content.lower()
                    for journal in [
                        "phytochemical analysis",
                        "john wiley",
                        "doi.org",
                        "elsevier",
                        "springer",
                    ]
                )
            ):
                continue

            # Include meaningful text content
            extracted_content.append(content)

    # Combine and clean the text
    combined = " ".join(extracted_content)

    # Remove excessive repetition (common in poorly extracted text)
    sentences = combined.split(". ")
    unique_sentences = []
    seen_sentences = set()

    for sentence in sentences:
        sentence_clean = sentence.strip().lower()
        # Skip very short sentences or ones we've already seen
        if len(sentence_clean) > 10 and sentence_clean not in seen_sentences:
            unique_sentences.append(sentence)
            seen_sentences.add(sentence_clean)

    combined = ". ".join(unique_sentences)

    # Clean up the text
    combined = combined.replace("\n", " ")
    combined = re.sub(r"\s+", " ", combined)
    combined = re.sub(r"\s+([.,;:?!])", r"\1", combined)
    combined = re.sub(r"\s*\|\s*", " | ", combined)
    combined = re.sub(r"\s*~\s*", " ", combined)
    combined = re.sub(r"[ŒœŸÿ]", "", combined)
    combined = re.sub(r"(\w)-\s+(\w)", r"\1\2", combined)
    combined = re.sub(r"\s+", " ", combined).strip()

    return combined


def extract_full_page_text(doc_json):
    """
    Extract all text content from the first few pages with optimized performance.

    Retrieves and concatenates text from early pages, excluding unwanted content
    like author information and affiliations.

    Args:
        doc_json (dict): The JSON representation of the document structure.

    Returns:
        str: Concatenated and cleaned text from the first few pages.

    Example:
        >>> text = extract_full_page_text(document_json)
        >>> print(len(text.split()))
        245
    """
    # Pre-compile patterns for speed
    metadata_indicators = {
        "correspondence:", "received:", "funding:", "doi:", "copyright",
        "@", "university", "institute", "department", "college", 
        "school of", "faculty of", "laboratory", "lab ", "center for", 
        "centre for", "hospital", "medical center", "research center", 
        "orcid", "author", "affiliation"
    }
    
    texts = doc_json.get("texts", [])
    if not texts:
        return ""
    
    early_page_texts = []
    
    # Single pass processing for first 3 pages
    for text in texts:
        content = text.get("text", "").strip()
        if not content or text.get("label") in ["page_header", "page_footer"]:
            continue
            
        # Get page number efficiently
        page_no = text.get("prov", [{}])[0].get("page_no", 1) if text.get("prov") else 1
        if page_no > 3:
            continue
            
        # Pre-compute content_lower once
        content_lower = content.lower()
        
        # Skip unwanted content efficiently
        if (not any(indicator in content_lower for indicator in metadata_indicators) and
            not _is_author_line(content)):
            early_page_texts.append(content)
    
    # Fallback if no content found
    if not early_page_texts:
        for text in texts[:30]:  # Limit for performance
            content = text.get("text", "").strip()
            if (content and 
                text.get("label") not in ["page_header", "page_footer"] and
                not any(indicator in content.lower() for indicator in metadata_indicators) and
                not _is_author_line(content)):
                early_page_texts.append(content)
    
    # Fast text cleaning with single regex operations
    full_text = " ".join(early_page_texts)
    if not full_text:
        return ""
        
    # Optimized regex operations
    full_text = re.sub(r'\s+', ' ', full_text.replace('\n', ' '))
    full_text = re.sub(r'\s*([.,;:?!])', r'\1', full_text)
    full_text = re.sub(r'\s*\|\s*', ' | ', full_text)
    full_text = re.sub(r'(\w)-\s+(\w)', r'\1\2', full_text)
    full_text = re.sub(r'[ŒœŸÿ~]', '', full_text).strip()
    
    return full_text
