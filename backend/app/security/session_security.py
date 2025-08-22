"""
Session security utilities for MARCUS application.
Implements session encryption and security features.
"""

import os
import json
import logging
import hashlib
import secrets
from typing import Dict, Any, Optional, Union
from datetime import datetime, timedelta
import base64

# Import cryptography with fallback
try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False
    logging.warning(
        "cryptography library not available. Session encryption will use basic encoding."
    )

    # Mock classes for development
    class Fernet:
        def __init__(self, key):
            self.key = key

        def encrypt(self, data):
            return base64.b64encode(data)

        def decrypt(self, data):
            return base64.b64decode(data)

    class hashes:
        class SHA256:
            pass

    class PBKDF2HMAC:
        def __init__(self, **kwargs):
            pass

        def derive(self, password):
            return password[:32].ljust(32, b"0")


logger = logging.getLogger(__name__)


class SessionEncryption:
    """Handles session data encryption and decryption."""

    def __init__(self, secret_key: Optional[str] = None):
        """
        Initialize session encryption.

        Args:
            secret_key: Base secret key for encryption (uses env var if not provided)
        """
        self.secret_key = secret_key or os.getenv("SECRET_KEY")
        if not self.secret_key:
            raise ValueError(
                "SECRET_KEY environment variable required for session encryption"
            )

        # Generate encryption key from secret
        self._encryption_key = self._derive_key(self.secret_key)
        self._fernet = Fernet(self._encryption_key)

    def _derive_key(self, password: str, salt: bytes = None) -> bytes:
        """Derive encryption key from password using PBKDF2."""
        if salt is None:
            # Use a fixed salt derived from the secret for consistency
            salt = hashlib.sha256(password.encode()).digest()[:16]

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,  # OWASP recommended minimum
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key

    def encrypt_session_data(self, data: Dict[str, Any]) -> str:
        """
        Encrypt session data for secure storage.

        Args:
            data: Session data to encrypt

        Returns:
            str: Encrypted session data as base64 string
        """
        try:
            # Convert to JSON and encrypt
            json_data = json.dumps(data, ensure_ascii=False)
            encrypted_data = self._fernet.encrypt(json_data.encode("utf-8"))
            return base64.urlsafe_b64encode(encrypted_data).decode("ascii")

        except Exception as e:
            logger.error(f"Session encryption failed: {e}")
            raise ValueError("Failed to encrypt session data")

    def decrypt_session_data(self, encrypted_data: str) -> Dict[str, Any]:
        """
        Decrypt session data from storage.

        Args:
            encrypted_data: Encrypted session data as base64 string

        Returns:
            dict: Decrypted session data
        """
        try:
            # Decode and decrypt
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_data.encode("ascii"))
            decrypted_data = self._fernet.decrypt(encrypted_bytes)
            return json.loads(decrypted_data.decode("utf-8"))

        except Exception as e:
            logger.error(f"Session decryption failed: {e}")
            raise ValueError(
                "Failed to decrypt session data - session may be corrupted or expired"
            )

    def generate_session_token(
        self, session_id: str, user_data: Dict[str, Any] = None
    ) -> str:
        """
        Generate an encrypted session token.

        Args:
            session_id: Unique session identifier
            user_data: Optional user data to include in token

        Returns:
            str: Encrypted session token
        """
        token_data = {
            "session_id": session_id,
            "created_at": datetime.utcnow().isoformat(),
            "user_data": user_data or {},
            "nonce": secrets.token_hex(16),  # Prevent replay attacks
        }

        return self.encrypt_session_data(token_data)

    def validate_session_token(
        self, token: str, max_age_hours: int = 24
    ) -> Dict[str, Any]:
        """
        Validate and decrypt session token.

        Args:
            token: Encrypted session token
            max_age_hours: Maximum age of token in hours

        Returns:
            dict: Decrypted token data

        Raises:
            ValueError: If token is invalid or expired
        """
        try:
            token_data = self.decrypt_session_data(token)

            # Validate required fields
            required_fields = ["session_id", "created_at", "user_data", "nonce"]
            for field in required_fields:
                if field not in token_data:
                    raise ValueError(f"Missing required field: {field}")

            # Check token age
            created_at = datetime.fromisoformat(token_data["created_at"])
            age = datetime.utcnow() - created_at

            if age > timedelta(hours=max_age_hours):
                raise ValueError(f"Token expired (age: {age}, max: {max_age_hours}h)")

            return token_data

        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid token format: {e}")
        except Exception as e:
            raise ValueError(f"Token validation failed: {e}")


class SessionSecurity:
    """Enhanced session security features."""

    def __init__(self, encryption: SessionEncryption):
        self.encryption = encryption
        self.active_sessions: Dict[str, Dict[str, Any]] = {}
        self.session_stats = {
            "created": 0,
            "expired": 0,
            "invalidated": 0,
            "hijack_attempts": 0,
        }

    def create_secure_session(
        self,
        session_id: str,
        user_data: Dict[str, Any] = None,
        client_info: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        Create a secure session with encryption and fingerprinting.

        Args:
            session_id: Unique session identifier
            user_data: User-related data
            client_info: Client fingerprint data (IP, User-Agent, etc.)

        Returns:
            dict: Session creation result with encrypted token
        """
        try:
            current_time = datetime.utcnow()

            # Generate session fingerprint for hijacking detection
            fingerprint = self._generate_client_fingerprint(client_info or {})

            session_data = {
                "session_id": session_id,
                "created_at": current_time.isoformat(),
                "last_activity": current_time.isoformat(),
                "user_data": user_data or {},
                "client_fingerprint": fingerprint,
                "activity_count": 0,
                "security_flags": {
                    "encrypted": True,
                    "fingerprinted": True,
                    "requires_reauth": False,
                },
            }

            # Store session
            self.active_sessions[session_id] = session_data

            # Generate encrypted token
            encrypted_token = self.encryption.generate_session_token(
                session_id, user_data
            )

            self.session_stats["created"] += 1

            logger.info(
                f"Secure session created: {session_id} (fingerprint: {fingerprint[:16]}...)"
            )

            return {
                "session_id": session_id,
                "encrypted_token": encrypted_token,
                "expires_at": (current_time + timedelta(hours=24)).isoformat(),
                "security_level": "high",
            }

        except Exception as e:
            logger.error(f"Failed to create secure session: {e}")
            raise ValueError("Session creation failed")

    def validate_session(
        self,
        session_id: str,
        encrypted_token: str = None,
        client_info: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        Validate session with security checks.

        Args:
            session_id: Session identifier
            encrypted_token: Optional encrypted token to validate
            client_info: Current client fingerprint data

        Returns:
            dict: Validation result
        """
        try:
            # Check if session exists
            if session_id not in self.active_sessions:
                return {"valid": False, "reason": "session_not_found"}

            session_data = self.active_sessions[session_id]
            current_time = datetime.utcnow()

            # Check expiration
            created_at = datetime.fromisoformat(session_data["created_at"])
            if current_time - created_at > timedelta(hours=24):
                self._expire_session(session_id)
                return {"valid": False, "reason": "session_expired"}

            # Validate encrypted token if provided
            if encrypted_token:
                try:
                    token_data = self.encryption.validate_session_token(encrypted_token)
                    if token_data["session_id"] != session_id:
                        logger.warning(
                            f"Session ID mismatch in token: {session_id} vs {token_data['session_id']}"
                        )
                        return {"valid": False, "reason": "token_session_mismatch"}
                except ValueError as e:
                    logger.warning(f"Invalid session token for {session_id}: {e}")
                    return {"valid": False, "reason": "invalid_token"}

            # Check for session hijacking
            if client_info:
                current_fingerprint = self._generate_client_fingerprint(client_info)
                stored_fingerprint = session_data.get("client_fingerprint", "")

                if not self._fingerprints_match(
                    stored_fingerprint, current_fingerprint
                ):
                    self.session_stats["hijack_attempts"] += 1
                    logger.warning(
                        f"Potential session hijacking detected for {session_id}: "
                        f"fingerprint mismatch {stored_fingerprint[:16]}... vs {current_fingerprint[:16]}..."
                    )

                    # Mark session for re-authentication
                    session_data["security_flags"]["requires_reauth"] = True
                    return {
                        "valid": False,
                        "reason": "fingerprint_mismatch",
                        "requires_reauth": True,
                    }

            # Update activity
            session_data["last_activity"] = current_time.isoformat()
            session_data["activity_count"] += 1

            return {
                "valid": True,
                "session_data": session_data,
                "activity_count": session_data["activity_count"],
                "last_activity": session_data["last_activity"],
            }

        except Exception as e:
            logger.error(f"Session validation error: {e}")
            return {"valid": False, "reason": "validation_error"}

    def invalidate_session(self, session_id: str, reason: str = "user_logout") -> bool:
        """
        Invalidate a session and clean up.

        Args:
            session_id: Session to invalidate
            reason: Reason for invalidation

        Returns:
            bool: True if session was invalidated
        """
        try:
            if session_id in self.active_sessions:
                del self.active_sessions[session_id]
                self.session_stats["invalidated"] += 1
                logger.info(f"Session invalidated: {session_id} (reason: {reason})")
                return True
            return False

        except Exception as e:
            logger.error(f"Session invalidation error: {e}")
            return False

    def cleanup_expired_sessions(self):
        """Clean up expired sessions."""
        current_time = datetime.utcnow()
        expired_sessions = []

        for session_id, session_data in self.active_sessions.items():
            created_at = datetime.fromisoformat(session_data["created_at"])
            if current_time - created_at > timedelta(hours=24):
                expired_sessions.append(session_id)

        for session_id in expired_sessions:
            self._expire_session(session_id)

        if expired_sessions:
            logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")

    def _expire_session(self, session_id: str):
        """Mark session as expired and remove it."""
        if session_id in self.active_sessions:
            del self.active_sessions[session_id]
            self.session_stats["expired"] += 1

    def _generate_client_fingerprint(self, client_info: Dict[str, Any]) -> str:
        """Generate client fingerprint for hijacking detection."""
        try:
            # Combine relevant client information
            fingerprint_data = {
                "ip": client_info.get("ip", ""),
                "user_agent": client_info.get("user_agent", ""),
                "accept_language": client_info.get("accept_language", ""),
                "screen_resolution": client_info.get("screen_resolution", ""),
                "timezone": client_info.get("timezone", ""),
            }

            # Create hash
            fingerprint_str = json.dumps(fingerprint_data, sort_keys=True)
            return hashlib.sha256(fingerprint_str.encode()).hexdigest()

        except Exception as e:
            logger.error(f"Fingerprint generation error: {e}")
            return hashlib.sha256(str(client_info).encode()).hexdigest()

    def _fingerprints_match(
        self, stored: str, current: str, tolerance: float = 0.8
    ) -> bool:
        """
        Compare fingerprints with tolerance for minor changes.

        Args:
            stored: Stored fingerprint
            current: Current fingerprint
            tolerance: Match tolerance (0.0 to 1.0)

        Returns:
            bool: True if fingerprints match within tolerance
        """
        if stored == current:
            return True

        # For now, require exact match for security
        # In production, could implement fuzzy matching for user agent changes, etc.
        return False

    def get_session_stats(self) -> Dict[str, Any]:
        """Get session security statistics."""
        return {
            **self.session_stats,
            "active_sessions": len(self.active_sessions),
            "oldest_session": self._get_oldest_session_age(),
            "average_activity": self._get_average_activity(),
        }

    def _get_oldest_session_age(self) -> Optional[float]:
        """Get age of oldest active session in hours."""
        if not self.active_sessions:
            return None

        current_time = datetime.utcnow()
        oldest_age = 0

        for session_data in self.active_sessions.values():
            created_at = datetime.fromisoformat(session_data["created_at"])
            age = (current_time - created_at).total_seconds() / 3600
            oldest_age = max(oldest_age, age)

        return round(oldest_age, 2)

    def _get_average_activity(self) -> float:
        """Get average activity count across sessions."""
        if not self.active_sessions:
            return 0.0

        total_activity = sum(
            session["activity_count"] for session in self.active_sessions.values()
        )
        return round(total_activity / len(self.active_sessions), 2)


# Global instances
try:
    session_encryption = SessionEncryption()
    session_security = SessionSecurity(session_encryption)
except Exception as e:
    logger.error(f"Failed to initialize session security: {e}")
    session_encryption = None
    session_security = None
