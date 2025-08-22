import os
import json
import re
import logging
from typing import Dict, List, Tuple, Any, Optional
from openai import OpenAI
from app.security.validators import APIKeyManager

# Configure logging
logger = logging.getLogger(__name__)

# Get API key from environment variable with validation
try:
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY environment variable is required")

    # Initialize secure API key manager
    api_key_manager = APIKeyManager(OPENAI_API_KEY)
    logger.info(f"OpenAI API key configured: {api_key_manager.get_masked_key()}")

except Exception as e:
    logger.error(f"OpenAI API key configuration failed: {e}")
    raise

# Initialize OpenAI client with validated key
client = OpenAI(api_key=api_key_manager.api_key)

# Use environment variable for model ID or fall back to the existing value
OPENAI_MODEL_ID = os.environ.get("OPENAI_MODEL_ID", "gpt-4")

try:
    retrieve_job_response = client.fine_tuning.jobs.retrieve(OPENAI_MODEL_ID)
    fine_tuned_model = retrieve_job_response.fine_tuned_model
    logger.info(f"Fine-tuned model configured: {fine_tuned_model}")
except Exception as e:
    logger.warning(f"Could not retrieve fine-tuned model, using base model: {e}")
    fine_tuned_model = OPENAI_MODEL_ID


def get_response(user_message: str, endpoint: str = "chat_completion") -> str:
    """
    Get response from OpenAI API using fine-tuned model with security logging

    Args:
        user_message (str): User message to process
        endpoint (str): API endpoint being used for logging

    Returns:
        str: OpenAI API response content
    """
    system_message = "Extract the compound information from the Paragraph."
    test_messages = []
    test_messages.append({"role": "system", "content": system_message})
    test_messages.append({"role": "user", "content": user_message})

    try:
        # Log API key usage for security monitoring
        api_key_manager.log_usage(endpoint)

        response = client.chat.completions.create(
            model=fine_tuned_model, messages=test_messages, temperature=0.3
        )

        result = response.choices[0].message.content
        logger.info(f"OpenAI API request successful for endpoint: {endpoint}")
        return result

    except Exception as e:
        logger.error(f"Error calling OpenAI API on {endpoint}: {str(e)}")
        # Don't expose API key in error messages
        sanitized_error = str(e).replace(OPENAI_API_KEY, "***REDACTED***")
        raise Exception(
            "OpenAI API error: An internal error occurred while processing your request."
        )


def find_positions(
    main_text: str, extracted_text: Dict[str, str]
) -> List[Dict[str, Any]]:
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
        values = [
            x.strip("' ") for x in values
        ]  # Clean string from trailing and leading whitespaces and apostrophes

        for value in values:
            if value != "nan" and value.strip():  # Skip empty or "nan" values
                matches = re.finditer(
                    re.escape(value), main_text
                )  # Use finditer to find all mentions

                for match in matches:
                    positions.append(
                        {
                            "label": label,
                            "start_offset": match.start(),
                            "end_offset": match.end(),
                        }
                    )

    return positions


def get_spans(user_message: str) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Extract spans from user message and handle JSON parsing errors gracefully.

    Args:
        user_message (str): Text to process

    Returns:
        tuple: (extracted_text, positions) or appropriate fallback
    """
    print(
        f"Processing message: {user_message[:100]}..."
        if len(user_message) > 100
        else user_message
    )

    # Get response
    try:
        extracted_text = get_response(user_message)
    except Exception as e:
        print(f"Error getting response: {str(e)}")
        return "", []

    # Print response for debugging
    print(f"Response received (length: {len(extracted_text)})")
    print(
        f"Response preview: {extracted_text[:200]}..."
        if len(extracted_text) > 200
        else extracted_text
    )

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
            potential_json = re.search(r"(\{.*\})", extracted_text, re.DOTALL)
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
