from fastapi import APIRouter, FastAPI

from marcus.api import security
from marcus.api.routes import events, health, images, papers, queue, segments, tools
from marcus.core.settings import get_settings


def create_app() -> FastAPI:
    settings = get_settings()  # invalid settings (e.g. trusted_proxies) stop startup here
    app = FastAPI(title="MARCUS v2", **security.fastapi_docs_kwargs(settings))
    api = APIRouter(prefix="/api/v2")
    api.include_router(health.router)
    api.include_router(papers.router)
    api.include_router(images.router)
    api.include_router(segments.router)
    api.include_router(queue.router)
    api.include_router(events.router)
    api.include_router(tools.router)
    app.include_router(api)
    security.install(app, settings)
    return app
