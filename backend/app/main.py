from __future__ import annotations

from fastapi import FastAPI

from .api import api_router


def create_app() -> FastAPI:
    fastapi_app = FastAPI(title="Job Search Intelligence API")
    fastapi_app.include_router(api_router)
    return fastapi_app


app = create_app()
