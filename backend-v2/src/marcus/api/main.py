import asyncio

from fastapi import APIRouter, FastAPI

from marcus.api import security
from marcus.api.routes import (
    annotation,
    events,
    health,
    images,
    papers,
    queue,
    rgroups,
    segments,
    tools,
)
from marcus.core.logging import configure_logging
from marcus.core.settings import get_settings


def create_app(json_logs: bool = False) -> FastAPI:
    """`json_logs=True` (the gunicorn command) installs the JSON log format for this process."""
    if json_logs:
        configure_logging("api")
    settings = get_settings()  # invalid settings (e.g. trusted_proxies) stop startup here
    app = FastAPI(title="MARCUS v2", **security.fastapi_docs_kwargs(settings))
    api = APIRouter(prefix="/api/v2")
    api.include_router(health.router)
    api.include_router(papers.router)
    api.include_router(annotation.router)
    api.include_router(rgroups.router)
    api.include_router(images.router)
    api.include_router(segments.router)
    api.include_router(queue.router)
    api.include_router(events.router)
    api.include_router(tools.router)
    app.include_router(api)
    # image uploads: bounded CPU-bound decodes per process (routes/images.py decode_image)
    app.state.decode_slots = asyncio.Semaphore(settings.image_decode_concurrency)
    # live Celery consumers, cached like /ready (the annotation and R-group routes check q.llm)
    app.state.live_queues = health.live_queues
    security.install(app, settings)
    return app
