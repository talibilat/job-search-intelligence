from __future__ import annotations

from fastapi import APIRouter

from .health import router as health_router
from .setup import router as setup_router
from .wipe_data import router as wipe_data_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(setup_router)
api_router.include_router(wipe_data_router)
