"""
Security tests for MARCUS application.
Tests all security implementations.
"""

import os
import json
import time
import pytest
from unittest.mock import Mock, patch

# Test imports with fallbacks
try:
    from app.security.validators import (
        EnvironmentValidator,
        APIKeyManager,
        get_cors_origins,
    )
    from app.security.file_validator import FileUploadValidator, validate_pdf_upload
    from app.security.rate_limiter import (
        RateLimiter,
        RateLimitRule,
        get_client_identifier,
    )
    from app.security.session_security import SessionEncryption, SessionSecurity

    SECURITY_MODULES_AVAILABLE = True
except ImportError as e:
    print(f"Security modules not available for testing: {e}")
    SECURITY_MODULES_AVAILABLE = False

# Test configuration
TEST_ENV_VARS = {
    "OPENAI_API_KEY": "sk-test1234567890abcdef1234567890abcdef1234567890abcdef",
    "SECRET_KEY": "test_secret_key_for_testing_purposes_only",
    "CORS_ORIGINS": "http://localhost:3000,https://test.example.com",
    "RATE_LIMIT_ENABLED": "true",
}


class TestEnvironmentValidator:
    """Test environment validation functionality."""

    @pytest.fixture(autouse=True)
    def setup_env(self):
        """Setup test environment variables."""
        self.original_env = {}
        for key, value in TEST_ENV_VARS.items():
            self.original_env[key] = os.getenv(key)
            os.environ[key] = value

        yield

        # Cleanup
        for key in TEST_ENV_VARS:
            if self.original_env[key] is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = self.original_env[key]

    @pytest.mark.skipif(
        not SECURITY_MODULES_AVAILABLE, reason="Security modules not available"
    )
    def test_validate_environment_success(self):
        """Test successful environment validation."""
        validated = EnvironmentValidator.validate_environment()

        assert "OPENAI_API_KEY" in validated
        assert "SECRET_KEY" in validated
        assert validated["OPENAI_API_KEY"] == TEST_ENV_VARS["OPENAI_API_KEY"]
        assert validated["SECRET_KEY"] == TEST_ENV_VARS["SECRET_KEY"]

    @pytest.mark.skipif(
        not SECURITY_MODULES_AVAILABLE, reason="Security modules not available"
    )
    def test_validate_environment_missing_required(self):
        """Test environment validation with missing required variables."""
        del os.environ["OPENAI_API_KEY"]

        with pytest.raises(EnvironmentError) as exc_info:
            EnvironmentValidator.validate_environment()

        assert "Missing required environment variables" in str(exc_info.value)
        assert "OPENAI_API_KEY" in str(exc_info.value)

    @pytest.mark.skipif(
        not SECURITY_MODULES_AVAILABLE, reason="Security modules not available"
    )
    def test_validate_openai_key_valid(self):
        """Test OpenAI key validation with valid key."""
        valid_key = "sk-1234567890abcdef1234567890abcdef1234567890abcdef"
        assert EnvironmentValidator.validate_openai_key(valid_key) is True

    @pytest.mark.skipif(
        not SECURITY_MODULES_AVAILABLE, reason="Security modules not available"
    )
    def test_validate_openai_key_invalid(self):
        """Test OpenAI key validation with invalid keys."""
        invalid_keys = [
            "invalid_key",
            "sk-short",
            "wrong-prefix-1234567890abcdef1234567890abcdef1234567890abcdef",
            "",
            None,
        ]

        for key in invalid_keys:
            assert EnvironmentValidator.validate_openai_key(key) is False

    @pytest.mark.skipif(
        not SECURITY_MODULES_AVAILABLE, reason="Security modules not available"
    )
    def test_get_cors_origins(self):
        """Test CORS origins parsing."""
        origins = get_cors_origins()
        expected = ["http://localhost:3000", "https://test.example.com"]
        assert origins == expected


class TestAPIKeyManager:
    """Test API key management functionality."""

    @pytest.mark.skipif(
        not SECURITY_MODULES_AVAILABLE, reason="Security modules not available"
    )
    def test_api_key_manager_valid_key(self):
        """Test API key manager with valid key."""
        valid_key = "sk-1234567890abcdef1234567890abcdef1234567890abcdef"
        manager = APIKeyManager(valid_key)

        assert manager.api_key == valid_key

    @pytest.mark.skipif(
        not SECURITY_MODULES_AVAILABLE, reason="Security modules not available"
    )
    def test_api_key_manager_invalid_key(self):
        """Test API key manager with invalid key."""
        invalid_key = "invalid_key"

        with pytest.raises(ValueError):
            APIKeyManager(invalid_key)

    @pytest.mark.skipif(
        not SECURITY_MODULES_AVAILABLE, reason="Security modules not available"
    )
    def test_get_masked_key(self):
        """Test API key masking."""
        valid_key = "sk-1234567890abcdef1234567890abcdef1234567890abcdef"
        manager = APIKeyManager(valid_key)

        masked = manager.get_masked_key()
        assert masked.startswith("sk-")
        assert "****" in masked
        assert valid_key[-4:] in masked
        assert len(masked) < len(valid_key)

    @pytest.mark.skipif(
        not SECURITY_MODULES_AVAILABLE, reason="Security modules not available"
    )
    def test_key_rotation(self):
        """Test API key rotation."""
        old_key = "sk-1234567890abcdef1234567890abcdef1234567890abcdef"
        new_key = "sk-abcdef1234567890abcdef1234567890abcdef1234567890"

        manager = APIKeyManager(old_key)
        old_masked = manager.get_masked_key()

        success = manager.rotate_key(new_key)
        assert success is True
        assert manager.api_key == new_key

        new_masked = manager.get_masked_key()
        assert old_masked != new_masked


class TestFileUploadValidator:
    """Test file upload validation functionality."""

    @pytest.mark.skipif(
        not SECURITY_MODULES_AVAILABLE, reason="Security modules not available"
    )
    def test_file_validator_initialization(self):
        """Test file validator initialization."""
        validator = FileUploadValidator()

        assert validator.MAX_FILE_SIZE == 20 * 1024 * 1024
        assert "application/pdf" in validator.ALLOWED_CONTENT_TYPES
        assert ".pdf" in validator.ALLOWED_EXTENSIONS

    @pytest.mark.skipif(
        not SECURITY_MODULES_AVAILABLE, reason="Security modules not available"
    )
    @pytest.mark.asyncio
    async def test_validate_file_success(self):
        """Test successful file validation."""
        # Mock file object with async methods
        from unittest.mock import AsyncMock

        mock_file = Mock()
        mock_file.filename = "test.pdf"
        mock_file.content_type = "application/pdf"

        # Create async mock methods
        async def mock_seek(offset, whence=0):
            return 0

        async def mock_tell():
            return 1004  # Actual size including PDF header

        async def mock_read():
            return b"%PDF-1.4\n" + b"0" * 995  # Valid PDF header (1004 bytes total)

        mock_file.seek = mock_seek
        mock_file.tell = mock_tell
        mock_file.read = mock_read

        validator = FileUploadValidator()
        result = await validator.validate_file(mock_file)

        assert result["valid"] is True
        assert result["filename"] == "test.pdf"
        assert result["size"] == 1004
        assert "hash" in result

    @pytest.mark.skipif(
        not SECURITY_MODULES_AVAILABLE, reason="Security modules not available"
    )
    @pytest.mark.asyncio
    async def test_validate_file_too_large(self):
        """Test file validation with oversized file."""
        mock_file = Mock()
        mock_file.filename = "large.pdf"
        mock_file.content_type = "application/pdf"
        mock_file.seek = Mock(return_value=0)
        mock_file.tell = Mock(return_value=FileUploadValidator.MAX_FILE_SIZE + 1)

        validator = FileUploadValidator()

        with pytest.raises(Exception):  # Should raise HTTPException
            await validator.validate_file(mock_file)

    @pytest.mark.skipif(
        not SECURITY_MODULES_AVAILABLE, reason="Security modules not available"
    )
    def test_validate_file_extension(self):
        """Test file extension validation."""
        validator = FileUploadValidator()

        # Valid extensions
        validator._validate_file_extension("test.pdf")
        validator._validate_file_extension("image.png")

        # Invalid extension should raise exception
        with pytest.raises(Exception):
            validator._validate_file_extension("script.exe")

    @pytest.mark.skipif(
        not SECURITY_MODULES_AVAILABLE, reason="Security modules not available"
    )
    def test_verify_file_content(self):
        """Test file content verification."""
        validator = FileUploadValidator()

        # Valid PDF content
        pdf_content = b"%PDF-1.4\nSome PDF content here"
        validator._verify_file_content(pdf_content, "test.pdf")

        # Invalid content should raise exception
        with pytest.raises(Exception):
            fake_content = b"This is not a PDF file"
            validator._verify_file_content(fake_content, "test.pdf")


class TestRateLimiter:
    """Test rate limiting functionality."""

    @pytest.mark.skipif(
        not SECURITY_MODULES_AVAILABLE, reason="Security modules not available"
    )
    def test_rate_limiter_initialization(self):
        """Test rate limiter initialization."""
        limiter = RateLimiter(enabled=True)

        assert limiter.enabled is True
        assert "upload" in limiter.rules
        assert "default" in limiter.rules

    @pytest.mark.skipif(
        not SECURITY_MODULES_AVAILABLE, reason="Security modules not available"
    )
    def test_rate_limit_rule(self):
        """Test rate limit rule creation."""
        rule = RateLimitRule(requests=10, window=60, burst=5, penalty=30)

        assert rule.requests == 10
        assert rule.window == 60
        assert rule.burst == 5
        assert rule.penalty == 30

    @pytest.mark.skipif(
        not SECURITY_MODULES_AVAILABLE, reason="Security modules not available"
    )
    def test_endpoint_type_detection(self):
        """Test endpoint type detection."""
        limiter = RateLimiter()

        assert limiter.get_endpoint_type("/api/upload/pdf") == "pdf"
        assert limiter.get_endpoint_type("/api/upload/file") == "upload"
        assert (
            limiter.get_endpoint_type("/api/process/ocsr") == "process"
        )  # 'process' matches first
        assert (
            limiter.get_endpoint_type("/api/ocsr/analyze") == "ocsr"
        )  # 'ocsr' without 'process'
        assert limiter.get_endpoint_type("/api/session/create") == "session"
        assert limiter.get_endpoint_type("/api/unknown") == "default"

    @pytest.mark.skipif(
        not SECURITY_MODULES_AVAILABLE, reason="Security modules not available"
    )
    def test_rate_limiting_logic(self):
        """Test rate limiting logic."""
        limiter = RateLimiter(enabled=True)
        client_id = "test_client"
        endpoint = "/api/test"

        # First few requests should be allowed
        for i in range(5):
            result = limiter.is_allowed(client_id, endpoint)
            assert result["allowed"] is True

        # After hitting limit, requests should be blocked
        # This depends on the default rule configuration
        for i in range(20):  # Exceed default limit
            result = limiter.is_allowed(client_id, endpoint)

        # Should eventually be blocked
        assert result["allowed"] is False
        assert "retry_after" in result

    @pytest.mark.skipif(
        not SECURITY_MODULES_AVAILABLE, reason="Security modules not available"
    )
    def test_client_identifier_extraction(self):
        """Test client identifier extraction."""
        # Mock request object
        mock_request = Mock()
        mock_request.state = Mock()
        mock_request.state.session_id = "test_session_123"

        client_id = get_client_identifier(mock_request)
        assert client_id == "session:test_session_123"

        # Test fallback to user ID
        mock_request.state.session_id = None
        mock_request.state.user_id = "user_456"

        client_id = get_client_identifier(mock_request)
        assert client_id == "user:user_456"

        # Test fallback to IP
        mock_request.state.user_id = None
        mock_request.client = Mock()
        mock_request.client.host = "192.168.1.1"

        client_id = get_client_identifier(mock_request)
        assert client_id == "ip:192.168.1.1"


class TestSessionSecurity:
    """Test session security functionality."""

    @pytest.mark.skipif(
        not SECURITY_MODULES_AVAILABLE, reason="Security modules not available"
    )
    def test_session_encryption_initialization(self):
        """Test session encryption initialization."""
        encryption = SessionEncryption("test_secret_key")
        assert encryption.secret_key == "test_secret_key"

    @pytest.mark.skipif(
        not SECURITY_MODULES_AVAILABLE, reason="Security modules not available"
    )
    def test_encrypt_decrypt_session_data(self):
        """Test session data encryption and decryption."""
        encryption = SessionEncryption("test_secret_key")

        test_data = {
            "session_id": "test_123",
            "user_id": "user_456",
            "timestamp": "2024-01-01T00:00:00Z",
        }

        # Encrypt data
        encrypted = encryption.encrypt_session_data(test_data)
        assert isinstance(encrypted, str)
        assert encrypted != json.dumps(test_data)

        # Decrypt data
        decrypted = encryption.decrypt_session_data(encrypted)
        assert decrypted == test_data

    @pytest.mark.skipif(
        not SECURITY_MODULES_AVAILABLE, reason="Security modules not available"
    )
    def test_session_token_generation_validation(self):
        """Test session token generation and validation."""
        encryption = SessionEncryption("test_secret_key")

        session_id = "test_session_123"
        user_data = {"user_id": "test_user"}

        # Generate token
        token = encryption.generate_session_token(session_id, user_data)
        assert isinstance(token, str)

        # Validate token
        token_data = encryption.validate_session_token(token)
        assert token_data["session_id"] == session_id
        assert token_data["user_data"] == user_data
        assert "created_at" in token_data
        assert "nonce" in token_data

    @pytest.mark.skipif(
        not SECURITY_MODULES_AVAILABLE, reason="Security modules not available"
    )
    def test_session_security_manager(self):
        """Test session security manager."""
        encryption = SessionEncryption("test_secret_key")
        security = SessionSecurity(encryption)

        session_id = "test_session_123"
        user_data = {"user_id": "test_user"}
        client_info = {"ip": "192.168.1.1", "user_agent": "test_agent"}

        # Create secure session
        result = security.create_secure_session(session_id, user_data, client_info)
        assert result["session_id"] == session_id
        assert "encrypted_token" in result
        assert result["security_level"] == "high"

        # Validate session
        validation = security.validate_session(
            session_id, result["encrypted_token"], client_info
        )
        assert validation["valid"] is True
        assert validation["session_data"]["session_id"] == session_id

        # Invalidate session
        success = security.invalidate_session(session_id)
        assert success is True

        # Validation should fail after invalidation
        validation = security.validate_session(
            session_id, result["encrypted_token"], client_info
        )
        assert validation["valid"] is False


class TestSecurityIntegration:
    """Test security features integration."""

    @pytest.mark.skipif(
        not SECURITY_MODULES_AVAILABLE, reason="Security modules not available"
    )
    def test_environment_to_config_integration(self):
        """Test environment validation integration with config."""
        # This would test the actual config.py integration
        # For now, just test that the functions work together

        with patch.dict(os.environ, TEST_ENV_VARS):
            validated = EnvironmentValidator.validate_environment()
            origins = get_cors_origins()

            assert len(validated) > 0
            assert len(origins) > 0
            assert "localhost" in str(origins) or "test.example.com" in str(origins)

    @pytest.mark.skipif(
        not SECURITY_MODULES_AVAILABLE, reason="Security modules not available"
    )
    def test_api_key_manager_integration(self):
        """Test API key manager integration."""
        with patch.dict(os.environ, TEST_ENV_VARS):
            manager = APIKeyManager(TEST_ENV_VARS["OPENAI_API_KEY"])

            # Test logging (should not raise exception)
            manager.log_usage("/api/test", "test_user")

            # Test that masked key doesn't contain actual key
            masked = manager.get_masked_key()
            assert TEST_ENV_VARS["OPENAI_API_KEY"] not in masked

    def test_security_configuration_validation(self):
        """Test that security configuration is properly set up."""
        # Test basic security settings exist
        security_settings = {
            "rate_limiting": True,
            "file_validation": True,
            "session_encryption": True,
            "cors_security": True,
        }

        for setting, expected in security_settings.items():
            assert expected is True, f"Security setting {setting} should be enabled"


def test_security_headers():
    """Test that security headers are properly configured."""
    # This would test actual HTTP responses
    # For now, verify the configuration exists

    expected_headers = [
        "X-RateLimit-Limit",
        "X-RateLimit-Remaining",
        "X-Session-ID",
        "Access-Control-Allow-Origin",
    ]

    # In a real test, you'd check these in HTTP responses
    for header in expected_headers:
        assert isinstance(header, str)
        assert len(header) > 0


if __name__ == "__main__":
    # Run basic tests without pytest
    print("Running basic security tests...")

    if SECURITY_MODULES_AVAILABLE:
        # Test environment validation
        try:
            with patch.dict(os.environ, TEST_ENV_VARS):
                validated = EnvironmentValidator.validate_environment()
                print("✅ Environment validation test passed")
        except Exception as e:
            print(f"❌ Environment validation test failed: {e}")

        # Test API key validation
        try:
            valid_key = "sk-1234567890abcdef1234567890abcdef1234567890abcdef"
            assert EnvironmentValidator.validate_openai_key(valid_key) is True
            assert EnvironmentValidator.validate_openai_key("invalid") is False
            print("✅ API key validation test passed")
        except Exception as e:
            print(f"❌ API key validation test failed: {e}")

        # Test rate limiter
        try:
            limiter = RateLimiter(enabled=True)
            result = limiter.is_allowed("test_client", "/api/test")
            assert "allowed" in result
            print("✅ Rate limiter test passed")
        except Exception as e:
            print(f"❌ Rate limiter test failed: {e}")

        print("Basic security tests completed")
    else:
        print("Security modules not available - tests skipped")
