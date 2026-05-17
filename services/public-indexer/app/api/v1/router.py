"""
Router principal da versao v1 da API do public-indexer.

Agrega sub-routers de health e admin sob o prefixo /api/v1.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints import admin, health

router = APIRouter()

# Registra sub-routers
router.include_router(health.router, tags=["health"])
router.include_router(
    admin.router,
    prefix="/admin",
    tags=["admin"],
)
