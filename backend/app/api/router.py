from __future__ import annotations

from fastapi import APIRouter

from .applications import router as applications_router
from .auth import router as auth_router
from .chat import router as chat_router
from .classification import router as classification_router
from .health import router as health_router
from .insights import router as insights_router
from .metrics import router as metrics_router
from .provider_config import router as provider_config_router
from .setup import router as setup_router
from .sync import router as sync_router
from .wipe_data import router as wipe_data_router

api_router = APIRouter()
api_router.include_router(applications_router)
api_router.include_router(auth_router)
api_router.include_router(chat_router)
api_router.include_router(classification_router)
api_router.include_router(health_router)
api_router.include_router(insights_router)
api_router.include_router(metrics_router)
api_router.include_router(provider_config_router)
api_router.include_router(setup_router)
api_router.include_router(sync_router)
api_router.include_router(wipe_data_router)
