"""
Aplicacao principal FastAPI.

Ponto de entrada do servico Python. Configura middleware, routers e
tratamento global de excecoes.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app

from app.api.v1.router import router as v1_router
from app.core.config import Settings
from app.core.logging import LoggingMiddleware, setup_logging
from app.core.metrics import MetricsMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ciclo de vida da aplicacao — startup e shutdown."""
    # TODO: inicializar conexoes (DB, Redis, MinIO) aqui
    yield
    # TODO: fechar conexoes aqui


def create_app() -> FastAPI:
    """Factory que cria e configura a aplicacao FastAPI."""
    settings = Settings()

    # Configura logging estruturado JSON
    setup_logging(level="DEBUG" if settings.DEBUG else "INFO")

    app = FastAPI(
        title=settings.APP_NAME,
        description="Agente Python para processamento de documentos, chat RAG, resumo e comparacao.",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Middleware de logging (deve vir antes para capturar todos os requests)
    app.add_middleware(LoggingMiddleware)

    # Middleware de metricas Prometheus
    app.add_middleware(MetricsMiddleware)

    # CORS para desenvolvimento
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Registra router v1
    app.include_router(v1_router, prefix="/api/v1")

    # Endpoint de metricas Prometheus
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)

    # Tratamento global de excecoes
    @app.exception_handler(Exception)
    async def global_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """Captura excecoes nao tratadas e retorna JSON padronizado."""
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "internal_server_error",
                "detail": str(exc) if settings.DEBUG else "Ocorreu um erro interno.",
            },
        )

    return app


app = create_app()
