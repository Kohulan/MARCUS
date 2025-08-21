from __future__ import annotations

import os
import logging

# Add environment variable loading
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Import configuration first to trigger environment validation
from app.config import CORS_ORIGINS, RATE_LIMIT_ENABLED

from fastapi import FastAPI
from fastapi import status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi_versioning import VersionedFastAPI

from .routers import docling_conversion
from .routers import open_ai_annotation
from .routers import decimer_segmentation
from .routers import ocsr_engine
from .routers import depiction_router
from .routers import similarity_router
from .routers import session_router
from app.exception_handlers import input_exception_handler
from app.exception_handlers import InvalidInputException
from app.middleware.session_middleware import SessionMiddleware
from app.schemas.healthcheck import HealthCheck

# Import security middleware
try:
    from app.middleware.rate_limit_middleware import RateLimitMiddleware
except ImportError:
    print(
        "⚠️  Rate limiting middleware not available - continuing without rate limiting"
    )
    RateLimitMiddleware = None

app = FastAPI(
    title="NP data extraction service",
    description="NP data extraction, a deep learning based text extraction service from journal articles for COCONUT",
    terms_of_service="https://decimer.ai",
    contact={
        "name": "Kohulan Rajan",
        "url": "https://cheminf.uni-jena.de/",
        "email": "kohulan.rajan@uni-jena.de",
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/license/MIT",
    },
)

app.include_router(docling_conversion.router)
app.include_router(open_ai_annotation.router)
app.include_router(decimer_segmentation.router)
app.include_router(ocsr_engine.router)
app.include_router(depiction_router.router)
app.include_router(similarity_router.router)

app = VersionedFastAPI(
    app,
    version_format="{major}",
    prefix_format="/v{major}",
    enable_latest=True,
    terms_of_service="https://decimer.ai",
    contact={
        "name": "Kohulan Rajan",
        "url": "https://cheminf.uni-jena.de/",
        "email": "kohulan.rajan@uni-jena.de",
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/license/MIT",
    },
    version=os.getenv("RELEASE_VERSION", "1.0"),
)

# Add session router AFTER versioning to avoid WebSocket versioning issues
app.include_router(session_router.router)

# Add security middleware first (rate limiting)
if RateLimitMiddleware and RATE_LIMIT_ENABLED:
    app.add_middleware(RateLimitMiddleware, enabled=RATE_LIMIT_ENABLED)
    print("✅ Rate limiting middleware enabled")
else:
    print("⚠️  Rate limiting disabled")

# Add session management middleware
app.add_middleware(SessionMiddleware)

# CORS configuration with security improvements
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,  # Use specific origins instead of "*"
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],  # Specific methods instead of "*"
    allow_headers=["Content-Type", "Authorization", "X-Session-ID"],  # Specific headers
)

print(f"✅ CORS configured with origins: {CORS_ORIGINS}")

# Remove the duplicate manual CORS middleware since we're using CORSMiddleware properly now

# register exception handlers
for sub_app in app.routes:
    if hasattr(sub_app.app, "add_exception_handler"):
        sub_app.app.add_exception_handler(
            InvalidInputException,
            input_exception_handler,
        )


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url=os.getenv("HOMEPAGE_URL", "/latest/docs"))


@app.get(
    "/health",
    tags=["healthcheck"],
    summary="Perform a Health Check",
    response_description="Return HTTP Status Code 200 (OK)",
    status_code=status.HTTP_200_OK,
    response_model=HealthCheck,
)
def get_health() -> HealthCheck:
    """## Perform a Health Check.

    Endpoint to perform a health check on. This endpoint can primarily be used by Docker
    to ensure a robust container orchestration and management are in place. Other
    services that rely on the proper functioning of the API service will not deploy if this
    endpoint returns any other HTTP status code except 200 (OK).
    Returns:
        HealthCheck: Returns a JSON response with the health status
    """
    return HealthCheck(status="OK")
