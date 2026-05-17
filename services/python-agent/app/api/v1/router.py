"""
Router principal da versao v1 da API.

Agrega todos os sub-routers de endpoints sob o prefixo /api/v1.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints import chat, compare, documents, health, research, summarize

router = APIRouter()

# Registra sub-routers
router.include_router(health.router, tags=["health"])
router.include_router(documents.router, prefix="/documents", tags=["documents"])
router.include_router(chat.router, prefix="/chat", tags=["chat"])
router.include_router(summarize.router, prefix="/summarize", tags=["summarize"])
router.include_router(compare.router, prefix="/compare", tags=["compare"])
router.include_router(research.router, prefix="/research", tags=["research"])
