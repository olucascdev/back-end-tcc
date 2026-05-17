"""
Endpoints de resumo de documentos.

Gera resumos estruturados de documentos processados usando SummarizeService.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.domain.summarize_service import SummarizeService
from app.schemas.contracts_v1 import SummarizeRequest, SummarizeResponse

router = APIRouter()


@router.post("/summarize-document", response_model=SummarizeResponse)
def summarize_document(req: SummarizeRequest) -> SummarizeResponse:
    """Gera resumo estruturado de um documento.

    Usa SummarizeService para buscar chunks relevantes no pgvector,
    chamar LLM e retornar resumo com 4 secoes: objective, methodology,
    results e conclusion.
    """
    service = SummarizeService()
    return service.summarize(
        project_id=str(req.project_id),
        document_id=str(req.document_id),
    )
