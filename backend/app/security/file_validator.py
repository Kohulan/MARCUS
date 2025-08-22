"""
File upload validation utilities for MARCUS application.
Implements comprehensive file validation.
"""

import os
import logging
from typing import Optional, List, Dict, Any
from pathlib import Path
import hashlib

# Import magic library with fallback
try:
    import magic

    HAS_MAGIC = True
except ImportError:
    HAS_MAGIC = False
    logging.warning(
        "python-magic not available. File type detection will use basic signature checking only."
    )

# Import FastAPI with fallback for type hints
try:
    from fastapi import UploadFile, HTTPException, status
except ImportError:
    # Define basic types for development/testing
    class UploadFile:
        pass

    class HTTPException(Exception):
        pass

    class status:
        HTTP_400_BAD_REQUEST = 400


logger = logging.getLogger(__name__)


class FileUploadValidator:
    """Comprehensive file upload validation."""

    # Configuration constants
    MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB
    ALLOWED_CONTENT_TYPES = {
        "application/pdf",
        "image/png",
        "image/jpeg",
        "image/jpg",
        "image/gif",
        "image/webp",
    }

    ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp"}

    # Magic number patterns for file type verification
    FILE_SIGNATURES = {
        "pdf": [b"%PDF-"],
        "png": [b"\x89PNG\r\n\x1a\n"],
        "jpeg": [b"\xff\xd8\xff"],
        "gif": [b"GIF87a", b"GIF89a"],
        "webp": [b"RIFF", b"WEBP"],  # WEBP has RIFF header followed by WEBP
    }

    def __init__(self):
        self.stats = {
            "total_uploads": 0,
            "rejected_size": 0,
            "rejected_type": 0,
            "rejected_content": 0,
            "accepted": 0,
        }

    async def validate_file(
        self, file: UploadFile, allowed_types: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Comprehensive file validation including size, type, and content verification.

        Args:
            file: The uploaded file to validate
            allowed_types: Optional list of specific content types to allow

        Returns:
            dict: Validation result with file info

        Raises:
            HTTPException: If validation fails
        """
        self.stats["total_uploads"] += 1

        try:
            # 1. Basic file checks
            if not file or not file.filename:
                self._reject("rejected_type", "No file provided or filename missing")

            # 2. Size validation
            await self._validate_file_size(file)

            # 3. Extension validation
            self._validate_file_extension(file.filename)

            # 4. Content type validation
            content_types = allowed_types or list(self.ALLOWED_CONTENT_TYPES)
            self._validate_content_type(file.content_type, content_types)

            # 5. Read file content for further validation
            content = await file.read()
            await file.seek(0)  # Reset file pointer

            # 6. Content verification (magic number check)
            self._verify_file_content(content, file.filename)

            # 7. Security checks
            self._security_checks(file.filename, content)

            # 8. Generate file hash for deduplication/tracking
            file_hash = hashlib.sha256(content).hexdigest()

            # Validation successful
            self.stats["accepted"] += 1

            validation_result = {
                "valid": True,
                "filename": file.filename,
                "content_type": file.content_type,
                "size": len(content),
                "hash": file_hash,
                "extension": Path(file.filename).suffix.lower(),
                "validated_at": self._get_timestamp(),
            }

            logger.info(
                f"File validation successful: {file.filename} ({len(content)} bytes)"
            )
            return validation_result

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Unexpected error during file validation: {str(e)}")
            self._reject("rejected_content", f"Validation error: {str(e)}")

    async def _validate_file_size(self, file: UploadFile):
        """Validate file size without reading entire content into memory."""
        try:
            # Try to get size from the file object
            current_pos = await file.seek(0, 2)  # Seek to end
            file_size = await file.tell()
            await file.seek(current_pos)  # Restore position

            if file_size > self.MAX_FILE_SIZE:
                self._reject(
                    "rejected_size",
                    f"File too large: {file_size} bytes (max: {self.MAX_FILE_SIZE} bytes)",
                )

        except Exception as e:
            # Fallback to reading content if seek/tell not supported
            logger.warning(f"Could not determine file size efficiently: {e}")
            content = await file.read()
            await file.seek(0)

            if len(content) > self.MAX_FILE_SIZE:
                self._reject(
                    "rejected_size",
                    f"File too large: {len(content)} bytes (max: {self.MAX_FILE_SIZE} bytes)",
                )

    def _validate_file_extension(self, filename: str):
        """Validate file extension."""
        extension = Path(filename).suffix.lower()

        if extension not in self.ALLOWED_EXTENSIONS:
            self._reject(
                "rejected_type",
                f"Invalid file extension: {extension}. Allowed: {', '.join(self.ALLOWED_EXTENSIONS)}",
            )

    def _validate_content_type(self, content_type: str, allowed_types: List[str]):
        """Validate MIME content type."""
        if content_type not in allowed_types:
            self._reject(
                "rejected_type",
                f"Invalid content type: {content_type}. Allowed: {', '.join(allowed_types)}",
            )

    def _verify_file_content(self, content: bytes, filename: str):
        """Verify file content matches extension using magic numbers."""
        if not content:
            self._reject("rejected_content", "Empty file content")

        extension = Path(filename).suffix.lower().lstrip(".")

        # Get expected signatures for this file type
        expected_signatures = self.FILE_SIGNATURES.get(extension, [])

        if expected_signatures:
            # Check if content starts with any of the expected signatures
            content_valid = False
            for signature in expected_signatures:
                if extension == "webp":
                    # Special handling for WEBP (RIFF header + WEBP identifier)
                    if content.startswith(b"RIFF") and b"WEBP" in content[:12]:
                        content_valid = True
                        break
                else:
                    if content.startswith(signature):
                        content_valid = True
                        break

            if not content_valid:
                self._reject(
                    "rejected_content",
                    f"File content does not match extension {extension}. Possible file type spoofing.",
                )

        # Additional libmagic verification if available
        if HAS_MAGIC:
            try:
                detected_type = magic.from_buffer(content, mime=True)
                logger.debug(f"Detected MIME type: {detected_type}")

                # Map detected type to expected types
                type_mapping = {
                    "application/pdf": ["pdf"],
                    "image/png": ["png"],
                    "image/jpeg": ["jpg", "jpeg"],
                    "image/gif": ["gif"],
                    "image/webp": ["webp"],
                }

                expected_extensions = []
                for mime_type, extensions in type_mapping.items():
                    if extension in extensions:
                        expected_extensions.append(mime_type)
                        break

                if expected_extensions and detected_type not in expected_extensions:
                    logger.warning(
                        f"MIME type mismatch: detected {detected_type}, expected one of {expected_extensions}"
                    )

            except Exception as e:
                logger.debug(f"Magic number detection failed: {e}")
        else:
            logger.debug(
                "Magic library not available, skipping advanced MIME detection"
            )

    def _security_checks(self, filename: str, content: bytes):
        """Additional security checks."""
        # 1. Check for suspicious filename patterns
        suspicious_patterns = [
            r"\.\./",  # Path traversal
            r'[<>:"|?*]',  # Invalid filename characters
            r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\.|$)",  # Windows reserved names
        ]

        import re

        for pattern in suspicious_patterns:
            if re.search(pattern, filename, re.IGNORECASE):
                self._reject(
                    "rejected_content",
                    f"Suspicious filename pattern detected: {filename}",
                )

        # 2. Check for embedded executables or scripts in content
        dangerous_signatures = [
            b"MZ",  # Windows executable
            b"\x7fELF",  # Linux executable
            b"#!/bin/",  # Shell script
            b"<?php",  # PHP script
            b"<script",  # JavaScript
        ]

        content_lower = content[:1024].lower()  # Check first 1KB
        for signature in dangerous_signatures:
            if signature.lower() in content_lower:
                logger.warning(f"Potentially dangerous content detected in {filename}")
                break

        # 3. Check file size consistency
        if len(content) == 0:
            self._reject("rejected_content", "Empty file not allowed")

        # 4. Check for overly long filenames
        if len(filename) > 255:
            self._reject("rejected_content", "Filename too long (max 255 characters)")

    def _reject(self, stat_key: str, message: str):
        """Helper to reject file and update statistics."""
        self.stats[stat_key] += 1
        logger.warning(f"File validation failed: {message}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)

    def _get_timestamp(self) -> str:
        """Get current timestamp for logging."""
        from datetime import datetime

        return datetime.utcnow().isoformat()

    def get_validation_stats(self) -> Dict[str, Any]:
        """Get validation statistics."""
        total = self.stats["total_uploads"]
        if total == 0:
            return self.stats

        return {
            **self.stats,
            "acceptance_rate": round((self.stats["accepted"] / total) * 100, 2),
            "rejection_rate": round(
                ((total - self.stats["accepted"]) / total) * 100, 2
            ),
        }

    def reset_stats(self):
        """Reset validation statistics."""
        for key in self.stats:
            self.stats[key] = 0


# Global validator instance
file_validator = FileUploadValidator()


# Utility functions for easy integration
async def validate_pdf_upload(file: UploadFile) -> Dict[str, Any]:
    """Validate PDF file upload."""
    return await file_validator.validate_file(file, ["application/pdf"])


async def validate_image_upload(file: UploadFile) -> Dict[str, Any]:
    """Validate image file upload."""
    image_types = ["image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp"]
    return await file_validator.validate_file(file, image_types)


async def validate_any_upload(file: UploadFile) -> Dict[str, Any]:
    """Validate any allowed file type upload."""
    return await file_validator.validate_file(file)
