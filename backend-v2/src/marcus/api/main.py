from fastapi import APIRouter, FastAPI

from marcus.api.routes import health


def create_app() -> FastAPI:
    app = FastAPI(title="MARCUS v2")
    api = APIRouter(prefix="/api/v2")
    api.include_router(health.router)
    app.include_router(api)
    return app
