"""
Endpoint de health check.

Verifica conectividade com todas as dependencias externas.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def health_check(request: Request) -> JSONResponse:
    """
    Health check basico — retorna 200 se servico esta vivo.

    Este endpoint nao verifica dependencias externas para ser leve.
    Use /health/ready para verificacao completa.
    """
    return JSONResponse(
        status_code=200,
        content={"status": "ok", "service": "public-indexer"},
    )


@router.get("/health/ready")
async def readiness_check(request: Request) -> JSONResponse:
    """
    Readiness check — verifica conectividade com todas as dependencias.

    Retorna 200 se todas as dependencias estao saudaveis,
    503 se alguma falhar.
    """
    checks: dict[str, str] = {}

    # PostgreSQL
    pg = getattr(request.app.state, "pg_client", None)
    if pg is not None:
        checks["postgresql"] = "ok" if pg.check_health() else "error"
    else:
        checks["postgresql"] = "not_configured"

    # MongoDB
    mongo = getattr(request.app.state, "mongo_client", None)
    if mongo is not None:
        try:
            mongo_ok = await mongo.check_health()
            checks["mongodb"] = "ok" if mongo_ok else "error"
        except Exception:
            checks["mongodb"] = "error"
    else:
        checks["mongodb"] = "not_configured"

    # MinIO
    minio = getattr(request.app.state, "minio_client", None)
    if minio is not None:
        checks["minio"] = "ok" if minio.check_health() else "error"
    else:
        checks["minio"] = "not_configured"

    # Redis
    redis = getattr(request.app.state, "redis_client", None)
    if redis is not None:
        try:
            redis_ok = await redis.check_health()
            checks["redis"] = "ok" if redis_ok else "error"
        except Exception:
            checks["redis"] = "error"
    else:
        checks["redis"] = "not_configured"

    # Determina status geral
    all_ok = all(v == "ok" for v in checks.values())
    status_code = 200 if all_ok else 503

    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if all_ok else "degraded",
            "checks": checks,
        },
    )
