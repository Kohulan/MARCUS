from fastapi import APIRouter, FastAPI

from marcus.api.routes import health, papers


def create_app() -> FastAPI:
    app = FastAPI(title="MARCUS v2")
    api = APIRouter(prefix="/api/v2")
    api.include_router(health.router)
    api.include_router(papers.router)
    app.include_router(api)
    return app
