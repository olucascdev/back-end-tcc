"""
Endpoints de health check e readiness.

Usados pelo gateway Go e orquestrador para verificar status do servico.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health_check() -> dict[str, str]:
    """Health check basico — indica que o servico esta no ar."""
    return {"status": "ok"}


@router.get("/ready")
def readiness_check() -> dict[str, str | dict[str, str]]:
    """Readiness check — verifica dependencias (mock por enquanto)."""
    return {
        "status": "ready",
        "checks": {
            "database": "ok",
        },
    }
