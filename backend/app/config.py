import os
from pathlib import Path
from app.security.validators import EnvironmentValidator, get_cors_origins

# Load environment variables from root .env file
try:
    from dotenv import load_dotenv

    # Try to load from multiple locations
    # 1. Root directory (for development)
    root_env_path = Path(__file__).parent.parent.parent / ".env"
    # 2. Current working directory (for Docker)
    cwd_env_path = Path.cwd() / ".env"

    print(f"🔍 Looking for .env files:")
    print(f"   Root path: {root_env_path} (exists: {root_env_path.exists()})")
    print(f"   CWD path: {cwd_env_path} (exists: {cwd_env_path.exists()})")

    # Load from root first, then override with cwd if it exists
    if root_env_path.exists():
        load_dotenv(root_env_path)
        print(f"✅ Loaded .env from {root_env_path}")
    if cwd_env_path.exists():
        load_dotenv(cwd_env_path, override=True)
        print(f"✅ Loaded .env from {cwd_env_path}")

    # Debug: Print current environment variables related to our app
    print(f"🔍 Environment variables:")
    print(f"   SECRET_KEY: {'SET' if os.getenv('SECRET_KEY') else 'NOT SET'}")
    print(f"   OPENAI_API_KEY: {'SET' if os.getenv('OPENAI_API_KEY') else 'NOT SET'}")

except ImportError:
    # dotenv not available, continue without it
    print("⚠️ dotenv not available, skipping .env file loading")
    pass

# Validate environment variables on startup
try:
    validated_env = EnvironmentValidator.validate_environment()
    print("✅ Environment validation successful")
except (EnvironmentError, ValueError) as e:
    print(f"❌ Environment validation failed: {e}")
    print("Please check your environment variables and try again.")
    exit(1)

# Base directory for the application (where the app is running)
BASE_DIR = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Directory for storing uploaded files and their processed output
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
PDF_DIR = os.path.join(UPLOAD_DIR, "pdfs")
SEGMENTS_DIR = os.path.join(UPLOAD_DIR, "segments")
IMAGES_DIR = os.path.join(UPLOAD_DIR, "chem_images")

# Create directories if they don't exist
os.makedirs(PDF_DIR, exist_ok=True)
os.makedirs(SEGMENTS_DIR, exist_ok=True)
os.makedirs(IMAGES_DIR, exist_ok=True)

# Security configuration
SECRET_KEY = validated_env["SECRET_KEY"]
OPENAI_API_KEY = validated_env["OPENAI_API_KEY"]
OPENAI_MODEL_ID = validated_env.get("OPENAI_MODEL_ID", "gpt-4")

# CORS configuration
CORS_ORIGINS = get_cors_origins()
print(f"✅ Configuration loaded:")
print(f"   - CORS Origins: {len(CORS_ORIGINS)} configured: {CORS_ORIGINS}")
print(
    f"   - Rate Limiting: {'Enabled' if validated_env.get('RATE_LIMIT_ENABLED', 'true').lower() == 'true' else 'Disabled'}"
)
print(f"   - Session Timeout: {validated_env.get('SESSION_TIMEOUT_HOURS', '24')} hours")
print(f"   - Max Upload Size: {20} MB")

# Rate limiting configuration
RATE_LIMIT_ENABLED = validated_env.get("RATE_LIMIT_ENABLED", "true").lower() == "true"

# Session configuration
SESSION_TIMEOUT_HOURS = int(validated_env.get("SESSION_TIMEOUT_HOURS", "24"))

# File upload security configuration
MAX_UPLOAD_SIZE = 20 * 1024 * 1024  # 20 MB
ALLOWED_FILE_TYPES = [
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/gif",
    "image/webp",
]

# Logging configuration for security events
SECURITY_LOG_LEVEL = os.getenv("SECURITY_LOG_LEVEL", "INFO")

print(f"✅ Configuration loaded:")
print(f"   - CORS Origins: {len(CORS_ORIGINS)} configured")
print(f"   - Rate Limiting: {'Enabled' if RATE_LIMIT_ENABLED else 'Disabled'}")
print(f"   - Session Timeout: {SESSION_TIMEOUT_HOURS} hours")
print(f"   - Max Upload Size: {MAX_UPLOAD_SIZE // (1024*1024)} MB")
