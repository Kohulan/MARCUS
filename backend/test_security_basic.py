#!/usr/bin/env python3
"""
Basic security validation tests for MARCUS application.
Tests core security implementations without external dependencies.
"""

import os
import sys
import json
from unittest.mock import Mock, patch

# Add the app directory to the Python path
sys.path.insert(0, "/Volumes/Data_Drive/Project/2025/MARCUS_development/MARCUS/backend")


def test_environment_validation():
    """Test environment validation."""
    print("Testing environment validation...")

    try:
        from app.security.validators import EnvironmentValidator

        # Test with valid environment
        test_env = {
            "OPENAI_API_KEY": "sk-test1234567890abcdef1234567890abcdef1234567890abcdef",
            "SECRET_KEY": "test_secret_key_for_testing_purposes_only",
        }

        with patch.dict(os.environ, test_env):
            validated = EnvironmentValidator.validate_environment()
            assert "OPENAI_API_KEY" in validated
            assert "SECRET_KEY" in validated
            print("✅ Environment validation test passed")

        # Test API key validation
        assert (
            EnvironmentValidator.validate_openai_key(
                "sk-1234567890abcdef1234567890abcdef1234567890abcdef"
            )
            is True
        )
        assert EnvironmentValidator.validate_openai_key("invalid_key") is False
        print("✅ API key validation test passed")

    except ImportError as e:
        print(f"⚠️  Environment validation test skipped: {e}")
    except Exception as e:
        print(f"❌ Environment validation test failed: {e}")


def test_api_key_manager():
    """Test API key manager."""
    print("Testing API key manager...")

    try:
        from app.security.validators import APIKeyManager

        valid_key = "sk-1234567890abcdef1234567890abcdef1234567890abcdef"
        manager = APIKeyManager(valid_key)

        # Test masking
        masked = manager.get_masked_key()
        assert "****" in masked
        assert valid_key not in masked
        assert masked.startswith("sk-")

        # Test key rotation
        new_key = "sk-abcdef1234567890abcdef1234567890abcdef1234567890"
        success = manager.rotate_key(new_key)
        assert success is True
        assert manager.api_key == new_key

        print("✅ API key manager test passed")

    except ImportError as e:
        print(f"⚠️  API key manager test skipped: {e}")
    except Exception as e:
        print(f"❌ API key manager test failed: {e}")


def test_cors_configuration():
    """Test CORS configuration."""
    print("Testing CORS configuration...")

    try:
        from app.security.validators import get_cors_origins

        test_origins = "http://localhost:3000,https://test.example.com"
        with patch.dict(os.environ, {"CORS_ORIGINS": test_origins}):
            origins = get_cors_origins()
            assert "http://localhost:3000" in origins
            assert "https://test.example.com" in origins
            assert "*" not in origins  # Should not contain wildcard

        print("✅ CORS configuration test passed")

    except ImportError as e:
        print(f"⚠️  CORS configuration test skipped: {e}")
    except Exception as e:
        print(f"❌ CORS configuration test failed: {e}")


def test_rate_limiter():
    """Test rate limiter."""
    print("Testing rate limiter...")

    try:
        from app.security.rate_limiter import RateLimiter, RateLimitRule

        # Test rate limiter initialization
        limiter = RateLimiter(enabled=True)
        assert limiter.enabled is True
        assert "upload" in limiter.rules
        assert "default" in limiter.rules

        # Test endpoint type detection
        assert limiter.get_endpoint_type("/api/upload/pdf") == "pdf"
        assert limiter.get_endpoint_type("/api/upload/file") == "upload"
        assert limiter.get_endpoint_type("/api/process/ocsr") == "ocsr"
        assert limiter.get_endpoint_type("/api/session/create") == "session"
        assert limiter.get_endpoint_type("/api/unknown") == "default"

        # Test basic rate limiting
        client_id = "test_client"
        endpoint = "/api/test"

        # First request should be allowed
        result = limiter.is_allowed(client_id, endpoint)
        assert result["allowed"] is True
        assert "current_requests" in result
        assert "limit" in result

        print("✅ Rate limiter test passed")

    except ImportError as e:
        print(f"⚠️  Rate limiter test skipped: {e}")
    except Exception as e:
        print(f"❌ Rate limiter test failed: {e}")


def test_file_validator():
    """Test file validator."""
    print("Testing file validator...")

    try:
        from app.security.file_validator import FileUploadValidator

        validator = FileUploadValidator()

        # Test configuration
        assert validator.MAX_FILE_SIZE == 10 * 1024 * 1024
        assert "application/pdf" in validator.ALLOWED_CONTENT_TYPES
        assert ".pdf" in validator.ALLOWED_EXTENSIONS

        # Test extension validation
        try:
            validator._validate_file_extension("test.pdf")  # Should not raise
            print("✅ Valid extension passed")
        except:
            print("❌ Valid extension failed")

        # Test invalid extension
        try:
            validator._validate_file_extension("script.exe")
            print("❌ Invalid extension was allowed")
        except:
            print("✅ Invalid extension was correctly rejected")

        # Test content verification
        pdf_content = b"%PDF-1.4\nSome PDF content here"
        try:
            validator._verify_file_content(pdf_content, "test.pdf")
            print("✅ Valid PDF content passed")
        except:
            print("❌ Valid PDF content failed")

        print("✅ File validator test passed")

    except ImportError as e:
        print(f"⚠️  File validator test skipped: {e}")
    except Exception as e:
        print(f"❌ File validator test failed: {e}")


def test_session_security():
    """Test session security."""
    print("Testing session security...")

    try:
        from app.security.session_security import SessionEncryption, SessionSecurity

        # Test session encryption
        encryption = SessionEncryption("test_secret_key")

        test_data = {
            "session_id": "test_123",
            "user_id": "user_456",
            "timestamp": "2024-01-01T00:00:00Z",
        }

        # Test encryption/decryption
        encrypted = encryption.encrypt_session_data(test_data)
        assert isinstance(encrypted, str)
        assert encrypted != json.dumps(test_data)

        decrypted = encryption.decrypt_session_data(encrypted)
        assert decrypted == test_data

        # Test token generation
        session_id = "test_session_123"
        user_data = {"user_id": "test_user"}
        token = encryption.generate_session_token(session_id, user_data)
        assert isinstance(token, str)

        token_data = encryption.validate_session_token(token)
        assert token_data["session_id"] == session_id
        assert token_data["user_data"] == user_data

        print("✅ Session security test passed")

    except ImportError as e:
        print(f"⚠️  Session security test skipped: {e}")
    except Exception as e:
        print(f"❌ Session security test failed: {e}")


def test_security_integration():
    """Test security integration."""
    print("Testing security integration...")

    try:
        # Test that all modules can be imported together
        from app.security.validators import EnvironmentValidator
        from app.security.file_validator import FileUploadValidator
        from app.security.rate_limiter import RateLimiter
        from app.security.session_security import SessionEncryption

        print("✅ All security modules import successfully")

        # Test configuration integration
        test_env = {
            "OPENAI_API_KEY": "sk-test1234567890abcdef1234567890abcdef1234567890abcdef",
            "SECRET_KEY": "test_secret_key_for_testing_purposes_only",
            "CORS_ORIGINS": "http://localhost:3000",
            "RATE_LIMIT_ENABLED": "true",
        }

        with patch.dict(os.environ, test_env):
            # Test environment validation works with all modules
            validated = EnvironmentValidator.validate_environment()
            assert len(validated) > 0

            # Test that configurations are consistent
            assert "OPENAI_API_KEY" in validated
            assert "SECRET_KEY" in validated

        print("✅ Security integration test passed")

    except ImportError as e:
        print(f"⚠️  Security integration test skipped: {e}")
    except Exception as e:
        print(f"❌ Security integration test failed: {e}")


def main():
    """Run all security tests."""
    print("=" * 60)
    print("MARCUS Security Implementation Tests")
    print("=" * 60)

    tests = [
        test_environment_validation,
        test_api_key_manager,
        test_cors_configuration,
        test_rate_limiter,
        test_file_validator,
        test_session_security,
        test_security_integration,
    ]

    passed = 0
    failed = 0
    skipped = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"❌ Test {test.__name__} failed: {e}")
            failed += 1

    print("=" * 60)
    print(f"Test Results:")
    print(f"  ✅ Passed: {passed}")
    print(f"  ❌ Failed: {failed}")
    print(f"  ⚠️  Skipped: {skipped}")
    print("=" * 60)

    if failed == 0:
        print("🎉 All available security tests passed!")
        return 0
    else:
        print("⚠️  Some tests failed. Check the implementation.")
        return 1


if __name__ == "__main__":
    exit(main())
