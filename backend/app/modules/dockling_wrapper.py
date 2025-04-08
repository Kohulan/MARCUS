import os
import json
import re

from fastapi import HTTPException, status, File, Form, UploadFile
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import EasyOcrOptions, PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from PyPDF2 import PdfReader, PdfWriter

artifacts_path = "/Users/kohulanrajan/.cache/docling/models"

pipeline_options = PdfPipelineOptions(artifacts_path=artifacts_path)
doc_converter = DocumentConverter(
    format_options={
        InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
    }
)


def extract_first_three_pages(input_pdf_path,number_of_pages=3):
    # Open the original PDF
    with open(input_pdf_path, 'rb') as input_pdf_file:
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
        with open(output_pdf_file_path, 'wb') as output_pdf_file:
            pdf_writer.write(output_pdf_file)
        print(output_pdf_file_path)
        return output_pdf_file_path

def get_converted_document(path,number_of_pages=3):
    output_pdf_file_path = extract_first_three_pages(path,number_of_pages)
    converter = DocumentConverter()
    conv_result: ConversionResult = converter.convert(output_pdf_file_path)
    conv_result_dict = conv_result.document.export_to_dict()
    return conv_result_dict

def extract_paper_content(doc_json):
    """
    Extract the title, abstract, and main text up to the results section from a document JSON.
    
    Args:
        doc_json (dict): The JSON representation of the document
        
    Returns:
        dict: A dictionary containing the title, abstract, and main text
    """
    title = ""
    abstract = ""
    main_text = []
    
    # Get all text elements
    texts = doc_json.get('texts', [])
    
    # Find the title (usually the first section_header with level 1)
    for text in texts:
        if text.get('label') == 'section_header' and text.get('level') == 1:
            if "RESULTS" not in text.get('text', '').upper() and len(text.get('text', '')) > 10:
                title = text.get('text', '')
                break
    
    # Find the abstract (usually a caption or text containing "ABSTRACT:")
    for text in texts:
        if "ABSTRACT:" in text.get('text', ''):
            abstract = text.get('text', '').replace("ABSTRACT:", "").strip()
            break
    
    # Extract main text up to results section
    found_abstract = False
    for text in texts:
        content = text.get('text', '')
        
        # Skip empty content
        if not content.strip():
            continue
            
        # Skip titles, headers, page numbers, etc.
        if text.get('label') in ['page_header', 'page_footer']:
            continue
            
        # Start collecting text after abstract
        if not found_abstract and "ABSTRACT:" in content:
            found_abstract = True
            continue
            
        # Stop at results section
        if found_abstract and (text.get('label') == 'section_header' and 
                              ("RESULTS" in content.upper() or "DISCUSSION" in content.upper())):
            break
            
        # Collect main text
        if found_abstract:
            main_text.append(content)
    
    # Join the main text paragraphs
    main_text_str = " ".join(main_text)
    
    return {
        "title": title,
        "abstract": abstract,
        "main_text": main_text_str
    }

def extract_from_docling_document(data):
    """
    Extract paper content from a Docling document format
    
    Args:
        data (dict): The Docling document JSON
        
    Returns:
        dict: A dictionary containing the title, abstract, and main text
    """
    # For Docling format, we need to extract the main document structure
    if 'schema_name' in data and data['schema_name'] == 'DoclingDocument':
        result = extract_paper_content(data)
        
        # Check if any of the key components are empty and extract additional info if needed
        if not result.get('title') or not result.get('abstract') or not result.get('main_text'):
            # Try to extract more text based on document structure
            texts = data.get('texts', [])
            
            # If title is empty, try to find a likely title
            if not result.get('title'):
                for text in texts:
                    # Look for large font text at the beginning
                    if (text.get('label') == 'paragraph' and 
                        text.get('page_number') == 1 and 
                        text.get('font_size', 0) > 12):  # Assuming larger font indicates title
                        result['title'] = text.get('text', '')
                        break
            
            # If abstract is empty, look for any text with "abstract" in it
            if not result.get('abstract'):
                for text in texts:
                    content = text.get('text', '').lower()
                    if 'abstract' in content:
                        result['abstract'] = text.get('text', '')
                        break
        
        return result
    else:
        return {"error": "Not a valid Docling document format"}

def combine_to_paragraph(result_dict):
    """
    Combine the title, abstract, and main text from extraction results into a single paragraph.
    
    Args:
        result_dict (dict): The dictionary containing 'title', 'abstract', and 'main_text'
        
    Returns:
        str: A single paragraph containing all the paper content
    """
    # Check for valid input
    if not isinstance(result_dict, dict):
        return "Error: Input must be a dictionary."
    
    # Extract components
    title = result_dict.get('title', '').strip()
    abstract = result_dict.get('abstract', '').strip()
    main_text = result_dict.get('main_text', '').strip()
    
    # Combine components with appropriate spacing
    combined_text = []
    
    if title:
        combined_text.append(title)
    
    if abstract:
        combined_text.append(abstract)
    
    if main_text:
        combined_text.append(main_text)
    
    # Join with spaces and clean up any double spaces
    combined_paragraph = ' '.join(combined_text)
    
    # Clean up the text - remove multiple spaces, normalize punctuation
    import re
    combined_paragraph = re.sub(r'\s+', ' ', combined_paragraph)
    combined_paragraph = re.sub(r'\s+([.,;:?!])', r'\1', combined_paragraph)
    
    return combined_paragraph

async def extract_pdf_text(
    pdf_file: UploadFile = File(...),
    pages: int = Form(1, description="Number of pages to process")
):
    """
    Upload a PDF file and extract its content as a combined text paragraph.
    
    Args:
        pdf_file: The PDF file to process
        pages: Number of pages to process (default: 1)
        
    Returns:
        JSON: Object containing the combined text
    """
    if not pdf_file.filename.lower().endswith('.pdf'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must be a PDF"
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
        
        return {"text": combined_text, "pdf_filename": safe_filename}
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing PDF: {str(e)}"
        )

def extract_full_page_text(doc_json):
    """
    Extract text from the entire first page of a document.
    
    Args:
        doc_json (dict): The JSON representation of the document
        
    Returns:
        str: The concatenated text from the first page
    """
    # Get all text elements
    texts = doc_json.get('texts', [])
    
    # Filter texts from the first page
    page_1_texts = []
    for text in texts:
        # Check if this text element is on page 1
        if text.get('page_number') == 1:  # Assuming page numbers start at 1
            content = text.get('text', '').strip()
            if content and text.get('label') not in ['page_header', 'page_footer']:
                page_1_texts.append(content)
    
    # If there's no specific page number field, try to get all texts
    # This is a fallback in case the document structure doesn't have page numbers
    if not page_1_texts and texts:
        # Just take all texts as a fallback
        for text in texts:
            content = text.get('text', '').strip()
            if content and text.get('label') not in ['page_header', 'page_footer']:
                page_1_texts.append(content)
    
    # Join all text elements with spaces
    full_text = ' '.join(page_1_texts)
    
    # Clean up the text
    full_text = re.sub(r'\s+', ' ', full_text)
    full_text = re.sub(r'\s+([.,;:?!])', r'\1', full_text)
    
    return full_text

