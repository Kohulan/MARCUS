import os
import json
import re
from typing import Dict, List, Tuple, Any, Optional
from openai import OpenAI

# Get API key from environment variable
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# Initialize OpenAI client
client = OpenAI(
    api_key=OPENAI_API_KEY
)

# Use environment variable for model ID or fall back to the existing value
OPENAI_MODEL_ID = os.environ.get("OPENAI_MODEL_ID")

retrieve_job_response = client.fine_tuning.jobs.retrieve(OPENAI_MODEL_ID)

fine_tuned_model = retrieve_job_response.fine_tuned_model

def get_response(user_message: str) -> str:
    """
    Get response from OpenAI API using fine-tuned model
    
    Args:
        user_message (str): User message to process
        
    Returns:
        str: OpenAI API response content
    """
    system_message = "Extract the compound information from the Paragraph."
    test_messages = []
    test_messages.append({"role": "system", "content": system_message})
    test_messages.append({"role": "user", "content": user_message})

    try:
        response = client.chat.completions.create(
            model=fine_tuned_model, messages=test_messages, temperature=0.3
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error calling OpenAI API: {str(e)}")
        raise

def find_positions(main_text: str, extracted_text: Dict[str, str]) -> List[Dict[str, Any]]:
    """
    Find positions of extracted entities in the main text
    
    Args:
        main_text (str): Original text
        extracted_text (dict): Dictionary of extracted entities
        
    Returns:
        list: List of dictionaries with label, start_offset, and end_offset
    """
    positions = []
    labels = list(extracted_text.keys())
    
    for label in labels:
        values = extracted_text[label].split(", ")
        values = [x.strip("' ") for x in values]  # Clean string from trailing and leading whitespaces and apostrophes
        
        for value in values:
            if value != "nan" and value.strip():  # Skip empty or "nan" values
                matches = re.finditer(re.escape(value), main_text)  # Use finditer to find all mentions
                
                for match in matches:
                    positions.append({
                        "label": label,
                        "start_offset": match.start(),
                        "end_offset": match.end(),
                    })

    return positions

def get_spans(user_message: str) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Extract spans from user message and handle JSON parsing errors gracefully.
    
    Args:
        user_message (str): Text to process
    
    Returns:
        tuple: (extracted_text, positions) or appropriate fallback
    """
    print(f"Processing message: {user_message[:100]}..." if len(user_message) > 100 else user_message)
    
    # Get response
    try:
        extracted_text = get_response(user_message)
    except Exception as e:
        print(f"Error getting response: {str(e)}")
        return "", []
    
    # Print response for debugging
    print(f"Response received (length: {len(extracted_text)})")
    print(f"Response preview: {extracted_text[:200]}..." if len(extracted_text) > 200 else extracted_text)
    
    # Handle empty response
    if not extracted_text or extracted_text.strip() == "":
        print("Warning: Empty response received")
        return "", []
    
    # Parse JSON with error handling
    try:
        data_dict = json.loads(extracted_text)
    except json.JSONDecodeError as e:
        print(f"JSON parsing error: {str(e)}")
        
        # Try to recover JSON from response if possible
        try:
            # Look for JSON-like patterns (text between curly braces)
            potential_json = re.search(r'(\{.*\})', extracted_text, re.DOTALL)
            if potential_json:
                cleaned_json = potential_json.group(1)
                print(f"Attempting to parse potential JSON: {cleaned_json[:100]}...")
                data_dict = json.loads(cleaned_json)
                positions = find_positions(user_message, data_dict)
                return cleaned_json, positions
        except Exception:
            pass  # If recovery fails, continue to fallback
            
        # Fallback when JSON parsing fails
        fallback_dict = {"spans": []}
        try:
            positions = find_positions(user_message, fallback_dict)
            return extracted_text, positions
        except Exception as pos_error:
            print(f"Error finding positions with fallback: {str(pos_error)}")
            return extracted_text, []
    
    # If JSON parsing succeeds, continue as normal
    try:
        positions = find_positions(user_message, data_dict)
        return extracted_text, positions
    except Exception as e:
        print(f"Error finding positions: {str(e)}")
        return extracted_text, []

def get_extracted_json(text: str) -> Dict[str, Any]:
    """
    Extract JSON data from text
    
    Args:
        text (str): Text to process
        
    Returns:
        dict: Extracted JSON data or error message
    """
    try:
        extracted_text, _ = get_spans(text)
        
        if not extracted_text:
            return {"error": "No data extracted"}
            
        # Try to parse as JSON
        try:
            json_data = json.loads(extracted_text)
            return json_data
        except json.JSONDecodeError:
            # Return as raw text if not valid JSON
            return {"raw_text": extracted_text}
            
    except Exception as e:
        return {"error": f"Error extracting data: {str(e)}"}

def get_extracted_positions(text: str) -> List[Dict[str, Any]]:
    """
    Extract positions from text
    
    Args:
        text (str): Text to process
        
    Returns:
        list: List of position dictionaries or empty list on error
    """
    try:
        _, positions = get_spans(text)
        return positions
    except Exception as e:
        print(f"Error extracting positions: {str(e)}")
        return []