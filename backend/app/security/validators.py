"""
Security utilities for MARCUS application.
Implements comprehensive security validations and utilities.
"""

import os
import re
import logging
from typing import Dict, List, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


class EnvironmentValidator:
    """Validates required environment variables on startup."""

    REQUIRED_VARS = ["OPENAI_API_KEY", "SECRET_KEY"]

    OPTIONAL_VARS = [
        "OPENAI_MODEL_ID",
        "CORS_ORIGINS",
        "RATE_LIMIT_ENABLED",
        "SESSION_TIMEOUT_HOURS",
    ]

    @classmethod
    def validate_environment(cls) -> Dict[str, str]:
        """
        Validate all required environment variables are present and valid.

        Returns:
            dict: Dictionary of validated environment variables

        Raises:
            EnvironmentError: If required variables are missing or invalid
        """
        missing_vars = []
        invalid_vars = []
        validated_vars = {}

        # Check required variables
        for var in cls.REQUIRED_VARS:
            value = os.getenv(var)
            if not value:
                # Skip SECRET_KEY here, handle it separately below
                if var != "SECRET_KEY":
                    missing_vars.append(var)
            else:
                # Validate specific variable formats
                if var == "OPENAI_API_KEY" and not cls.validate_openai_key(value):
                    invalid_vars.append(f"{var} (invalid format)")
                else:
                    validated_vars[var] = value

        # Check optional variables with defaults
        for var in cls.OPTIONAL_VARS:
            value = os.getenv(var)
            if value:
                validated_vars[var] = value

        # Set defaults for optional variables
        if "CORS_ORIGINS" not in validated_vars:
            validated_vars["CORS_ORIGINS"] = "http://localhost:8080"
        if "RATE_LIMIT_ENABLED" not in validated_vars:
            validated_vars["RATE_LIMIT_ENABLED"] = "true"
        if "SESSION_TIMEOUT_HOURS" not in validated_vars:
            validated_vars["SESSION_TIMEOUT_HOURS"] = "24"
        if "OPENAI_MODEL_ID" not in validated_vars:
            validated_vars["OPENAI_MODEL_ID"] = "gpt-4"

        # Generate SECRET_KEY if not provided (for development only)
        if "SECRET_KEY" not in validated_vars:
            if os.getenv("NODE_ENV") == "development":
                import secrets

                validated_vars["SECRET_KEY"] = secrets.token_urlsafe(32)
                logger.warning(
                    "Generated temporary SECRET_KEY for development. Set SECRET_KEY environment variable for production."
                )
            else:
                missing_vars.append("SECRET_KEY")

        if missing_vars:
            raise EnvironmentError(
                f"Missing required environment variables: {missing_vars}"
            )

        if invalid_vars:
            raise ValueError(f"Invalid environment variables: {invalid_vars}")

        logger.info(
            f"Environment validation successful. Loaded {len(validated_vars)} variables."
        )
        return validated_vars

    @staticmethod
    def validate_openai_key(key: str) -> bool:
        """
        Validate OpenAI API key format.

        Args:
            key: The API key to validate

        Returns:
            bool: True if key format is valid
        """
        if not key or not isinstance(key, str):
            return False

        # OpenAI API keys start with 'sk-' and have specific length
        if not key.startswith("sk-"):
            return False

        # Check minimum length (OpenAI keys are typically 51+ characters)
        if len(key) < 51:
            return False

        # Check for valid characters (alphanumeric and some special chars)
        if not re.match(r"^sk-[A-Za-z0-9\-_]+$", key):
            return False

        return True


class APIKeyManager:
    """Manages API key security and rotation."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._validate_key()

    def _validate_key(self):
        """Validate the API key on initialization."""
        if not EnvironmentValidator.validate_openai_key(self.api_key):
            raise ValueError("Invalid OpenAI API key format")

    def get_masked_key(self) -> str:
        """
        Get a masked version of the API key for logging.

        Returns:
            str: Masked API key (e.g., "sk-****...****1234")
        """
        if len(self.api_key) < 10:
            return "sk-****"

        return f"{self.api_key[:3]}****...****{self.api_key[-4:]}"

    def log_usage(self, endpoint: str, user_id: Optional[str] = None):
        """
        Log API key usage without exposing the actual key.

        Args:
            endpoint: The endpoint where the key was used
            user_id: Optional user identifier
        """
        logger.info(
            f"API key used - Endpoint: {endpoint}, User: {user_id or 'anonymous'}, Key: {self.get_masked_key()}"
        )

    def rotate_key(self, new_key: str) -> bool:
        """
        Rotate to a new API key.

        Args:
            new_key: The new API key

        Returns:
            bool: True if rotation successful
        """
        if not EnvironmentValidator.validate_openai_key(new_key):
            logger.error("Key rotation failed: Invalid new key format")
            return False

        old_masked = self.get_masked_key()
        self.api_key = new_key
        new_masked = self.get_masked_key()

        logger.info(f"API key rotated from {old_masked} to {new_masked}")
        return True


def get_cors_origins() -> List[str]:
    """
    Get CORS origins from environment with validation.

    Returns:
        list: List of validated CORS origins
    """
    cors_origins_str = os.getenv("CORS_ORIGINS", "http://localhost:8080")

    # Split by comma and clean up
    origins = [origin.strip() for origin in cors_origins_str.split(",")]

    # Validate each origin
    validated_origins = []
    for origin in origins:
        if origin == "*":
            logger.warning(
                "Wildcard CORS origin detected. This should only be used in development."
            )
            validated_origins.append(origin)
        elif origin.startswith(("http://", "https://")):
            validated_origins.append(origin)
        else:
            logger.warning(f"Invalid CORS origin format: {origin}. Skipping.")

    if not validated_origins:
        logger.warning("No valid CORS origins found. Using default localhost.")
        validated_origins = ["http://localhost:8080"]

    logger.info(f"CORS origins configured: {validated_origins}")
    return validated_origins
