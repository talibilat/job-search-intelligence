from __future__ import annotations

from fastapi import FastAPI

from .api import api_router
from .api.errors import register_exception_handlers


def create_app() -> FastAPI:
    fastapi_app = FastAPI(title="Job Search Intelligence API")
    fastapi_app.include_router(api_router)
    register_exception_handlers(fastapi_app)
    return fastapi_app


app = create_app()
