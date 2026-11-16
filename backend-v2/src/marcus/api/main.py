from fastapi import APIRouter, FastAPI

from marcus.api.routes import events, health, images, papers, queue, segments, tools


def create_app() -> FastAPI:
    app = FastAPI(title="MARCUS v2")
    api = APIRouter(prefix="/api/v2")
    api.include_router(health.router)
    api.include_router(papers.router)
    api.include_router(images.router)
    api.include_router(segments.router)
    api.include_router(queue.router)
    api.include_router(events.router)
    api.include_router(tools.router)
    app.include_router(api)
    return app
