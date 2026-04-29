"""
Aplicacao principal FastAPI do public-indexer.

Ponto de entrada do servico. Configura lifespan events, middleware,
routers e injecao de dependencias.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import Depends, FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app

from app.api.v1.router import router as v1_router
from app.api.v1.endpoints import admin as admin_endpoints
from app.application.usecases import GetJobStatusUseCase, RunIndexUseCase
from app.application.catalog_sync import CatalogSyncUseCase
from app.application.artifact_processor import ArtifactProcessorUseCase
from app.application.embedding_processor import EmbeddingProcessorUseCase
from app.application.job_reporter import JobReporter
from app.core.config import Settings
from app.core.logging import LoggingMiddleware, setup_logging
from app.domain.services import BookCatalogService, JobStore
from app.infrastructure.clients import (
    MinIOClient,
    MongoDBClient,
    PostgresClient,
    RedisClient,
)
from app.infrastructure.sources import (
    create_open_library_client,
    create_gutenberg_client,
)
from app.infrastructure.artifact_storage import ArtifactStorageService
from app.infrastructure.chunking import ChunkingConfig, TextChunker
from app.infrastructure.embedder import OpenAIEmbedder
from app.infrastructure.text_extraction import TextExtractor
from app.infrastructure.vector_store import PublicVectorStore
from app.infrastructure.dlq import FailureTracker
from app.infrastructure.scheduler import IndexScheduler

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Ciclo de vida da aplicacao — startup e shutdown.

    Startup:
    - Conecta PostgreSQL, MongoDB, MinIO, Redis
    - Inicializa servicos de dominio e casos de uso
    - Inicia scheduler de indexacao periodica

    Shutdown:
    - Para scheduler
    - Fecha todas as conexoes
    """
    settings: Settings = app.state.settings

    # --- Startup: conecta todos os clientes ---
    logger.info("Inicializando public-indexer...")

    # PostgreSQL
    pg_client = PostgresClient(settings)
    await pg_client.connect()

    # MongoDB
    mongo_client = MongoDBClient(settings)
    await mongo_client.connect()

    # MinIO (sync)
    minio_client = MinIOClient(settings)
    minio_client.connect()

    # Redis
    redis_client = RedisClient(settings)
    await redis_client.connect()

    # Servicos de dominio
    book_catalog = BookCatalogService(mongo_client.db)
    job_store = JobStore()

    # Clientes de fontes externas
    open_library_client = create_open_library_client(settings)
    gutenberg_client = create_gutenberg_client(settings)

    # Servico de armazenamento de artefatos
    artifact_storage = ArtifactStorageService(
        settings=settings,
        minio_client=minio_client.client,
    )

    # Infraestrutura de embeddings (Feature 5.4)
    text_extractor = TextExtractor()
    text_chunker = TextChunker(config=ChunkingConfig())
    embedder = OpenAIEmbedder(
        api_key=getattr(settings, "OPENAI_API_KEY", ""),
        max_retries=settings.MAX_RETRIES,
    )
    vector_store = PublicVectorStore(pg_client=pg_client)

    # Failure tracker (Feature 5.5)
    failure_tracker = FailureTracker(mongo_client.db)

    # Job reporter (Feature 5.6)
    job_reporter = JobReporter(mongo_client.db)

    # Casos de uso
    artifact_processor = ArtifactProcessorUseCase(
        book_catalog=book_catalog,
        artifact_storage=artifact_storage,
    )

    embedding_processor = EmbeddingProcessorUseCase(
        artifact_storage=artifact_storage,
        text_extractor=text_extractor,
        text_chunker=text_chunker,
        embedder=embedder,
        vector_store=vector_store,
        book_catalog=book_catalog,
    )

    run_index_usecase = RunIndexUseCase(
        book_catalog=book_catalog,
        job_store=job_store,
        artifact_processor=artifact_processor,
        embedding_processor=embedding_processor,
        failure_tracker=failure_tracker,
        job_reporter=job_reporter,
    )

    get_job_usecase = GetJobStatusUseCase(job_store)

    catalog_sync_usecase = CatalogSyncUseCase(
        book_catalog=book_catalog,
        open_library_client=open_library_client,
        gutenberg_client=gutenberg_client,
        batch_size=settings.BATCH_SIZE,
    )

    # Scheduler (Feature 5.5)
    scheduler = IndexScheduler(
        redis_client=redis_client.client,
        catalog_sync=catalog_sync_usecase,
        run_index=run_index_usecase,
        sync_interval_minutes=settings.SYNC_INTERVAL_MINUTES,
    )

    # Inicia scheduler em background
    await scheduler.start()

    # Registra dependencias FastAPI
    async def _provide_run_uc() -> RunIndexUseCase:
        return run_index_usecase

    async def _provide_get_uc() -> GetJobStatusUseCase:
        return get_job_usecase

    async def _provide_catalog_sync_uc() -> CatalogSyncUseCase:
        return catalog_sync_usecase

    app.dependency_overrides[admin_endpoints._get_run_index_usecase] = _provide_run_uc
    app.dependency_overrides[admin_endpoints._get_get_job_usecase] = _provide_get_uc
    app.dependency_overrides[admin_endpoints._get_catalog_sync_usecase] = (
        _provide_catalog_sync_uc
    )

    # Armazena no app state para acesso direto
    app.state.pg_client = pg_client
    app.state.mongo_client = mongo_client
    app.state.minio_client = minio_client
    app.state.redis_client = redis_client
    app.state.scheduler = scheduler

    logger.info("Public-indexer inicializado com sucesso")

    yield

    # --- Shutdown: fecha todas as conexoes ---
    logger.info("Encerrando public-indexer...")

    # Para scheduler gracefulmente
    await scheduler.stop()

    await pg_client.close()
    await mongo_client.close()
    minio_client.close()
    await redis_client.close()

    logger.info("Public-indexer encerrado")


def create_app() -> FastAPI:
    """Factory que cria e configura a aplicacao FastAPI."""
    settings = Settings()

    # Configura logging estruturado JSON
    setup_logging(level="DEBUG" if settings.DEBUG else "INFO")

    app = FastAPI(
        title=settings.APP_NAME,
        description="Servico de indexacao de acervo publico (Open Library, Project Gutenberg, Google Books).",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Armazena settings no app state
    app.state.settings = settings

    # Middleware de logging (deve vir antes para capturar todos os requests)
    app.add_middleware(LoggingMiddleware)

    # CORS para desenvolvimento
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Headers de seguranca em todas as respostas
    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        """Injeta headers de seguranca HTTP em todas as respostas."""
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        # HSTS apenas quando nao estiver em modo debug
        if not settings.DEBUG:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response

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
        logger.exception("Excecao nao tratada: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "internal_server_error",
                "detail": str(exc) if settings.DEBUG else "Ocorreu um erro interno.",
            },
        )

    return app


app = create_app()
