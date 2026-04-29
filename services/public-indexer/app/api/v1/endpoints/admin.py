"""
Endpoints administrativos para controle de indexacao.

Permite disparar indexacao manual, sincronizar catalogo
e consultar status de jobs.
"""

from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.application.usecases import GetJobStatusUseCase, RunIndexUseCase

logger = logging.getLogger(__name__)

router = APIRouter()


async def verify_admin_api_key(request: Request) -> None:
    """
    Dependencia que valida a chave de administracao via header.

    Verifica se o header X-Admin-API-Key esta presente e corresponde
    a chave configurada em ADMIN_API_KEY.

    Raises:
        HTTPException: 403 se a chave estiver ausente ou invalida.
    """
    from app.core.config import Settings

    settings = Settings()
    admin_key = settings.ADMIN_API_KEY

    # Se ADMIN_API_KEY nao estiver configurada, permite acesso (dev mode)
    if not admin_key:
        logger.warning("ADMIN_API_KEY nao configurada — endpoints admin abertos")
        return

    provided_key = request.headers.get("X-Admin-API-Key")
    if not provided_key:
        raise HTTPException(
            status_code=403,
            detail="Header X-Admin-API-Key obrigatorio",
        )
    if provided_key != admin_key:
        raise HTTPException(
            status_code=403,
            detail="Chave de administracao invalida",
        )


class IndexRunRequest(BaseModel):
    """Corpo opcional para disparar indexacao."""

    source_filter: Optional[str] = Field(
        default=None,
        description="Filtro de fonte (ex: 'gutenberg', 'openlibrary')",
    )
    dry_run: bool = Field(
        default=False,
        description="Se True, apenas simula sem persistir embeddings",
    )


class IndexRunResponse(BaseModel):
    """Resposta com job_id criado."""

    job_id: UUID
    status: str
    dry_run: bool


class JobStatusResponse(BaseModel):
    """Resposta com status detalhado do job."""

    job_id: UUID
    status: str
    source_filter: Optional[str] = None
    dry_run: bool = False
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None
    items_processed: int = 0


class CatalogSyncRequest(BaseModel):
    """Corpo opcional para sincronizacao de catalogo."""

    source_filter: Optional[str] = Field(
        default=None,
        description="Filtro de fonte (ex: 'gutenberg', 'openlibrary')",
    )


class CatalogSyncReportItem(BaseModel):
    """Relatorio de sincronizacao por fonte."""

    source: str
    new: int
    updated: int
    unchanged: int
    errors: int


class CatalogSyncResponse(BaseModel):
    """Resposta com relatorio de sincronizacao."""

    reports: list[CatalogSyncReportItem]


async def _get_run_index_usecase() -> RunIndexUseCase:
    """Dependency: retorna caso de uso de indexacao do app state."""
    from fastapi import Request

    # This will be overridden in tests via app.dependency_overrides
    raise NotImplementedError("Use dependency_overrides in tests")


async def _get_get_job_usecase() -> GetJobStatusUseCase:
    """Dependency: retorna caso de uso de consulta de job do app state."""
    raise NotImplementedError("Use dependency_overrides in tests")


async def _get_catalog_sync_usecase():
    """Dependency: retorna caso de uso de sincronizacao de catalogo."""
    from fastapi import Request

    raise NotImplementedError("Use dependency_overrides in tests")


@router.post("/index/run", response_model=IndexRunResponse)
async def run_index(
    body: IndexRunRequest | None = None,
    use_case: RunIndexUseCase = Depends(_get_run_index_usecase),
    _admin: None = Depends(verify_admin_api_key),
) -> IndexRunResponse:
    """
    Dispara execucao de indexacao de acervo publico.

    Retorna job_id para acompanhamento assincrono.
    """
    source_filter = body.source_filter if body else None
    dry_run = body.dry_run if body else False

    job = await use_case.execute(
        source_filter=source_filter,
        dry_run=dry_run,
    )

    return IndexRunResponse(
        job_id=job.job_id,
        status=job.status.value,
        dry_run=job.dry_run,
    )


@router.get("/index/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: UUID,
    use_case: GetJobStatusUseCase = Depends(_get_get_job_usecase),
) -> JobStatusResponse:
    """
    Retorna status de um job de indexacao.

    Status possiveis: pending, running, completed, failed.
    """
    job = use_case.execute(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} nao encontrado")

    return JobStatusResponse(
        job_id=job.job_id,
        status=job.status.value,
        source_filter=job.source_filter,
        dry_run=job.dry_run,
        created_at=job.created_at.isoformat(),
        started_at=job.started_at.isoformat() if job.started_at else None,
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
        error_message=job.error_message,
        items_processed=job.items_processed,
    )


@router.post("/catalog/sync", response_model=CatalogSyncResponse)
async def sync_catalog(
    body: CatalogSyncRequest | None = None,
    use_case=Depends(_get_catalog_sync_usecase),
    _admin: None = Depends(verify_admin_api_key),
) -> CatalogSyncResponse:
    """
    Dispara sincronizacao de catalogo de fontes externas.

    Busca metadados do Open Library e/ou Project Gutenberg,
    deduplica por stable_key e persiste no MongoDB.

    Retorna relatorio com contagens por fonte.
    """
    source_filter = body.source_filter if body else None

    reports = await use_case.execute(source_filter=source_filter)

    report_items = [
        CatalogSyncReportItem(
            source=report.source,
            new=report.new,
            updated=report.updated,
            unchanged=report.unchanged,
            errors=report.errors,
        )
        for report in reports.values()
    ]

    return CatalogSyncResponse(reports=report_items)
