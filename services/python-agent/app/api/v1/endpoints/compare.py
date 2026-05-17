"""
Endpoints de comparacao de documentos.

Compara dois ou mais documentos sob um tema especifico usando CompareService.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.domain.compare_service import CompareService
from app.schemas.contracts_v1 import CompareRequest, CompareResponse

router = APIRouter()


@router.post("/compare-documents", response_model=CompareResponse)
def compare_documents(req: CompareRequest) -> CompareResponse:
    """Compara documentos sob um tema especifico.

    Usa CompareService para buscar chunks relevantes no pgvector,
    agrupar por documento, chamar LLM e retornar comparacao tematica
    estruturada com similarities, differences e synthesis.
    """
    service = CompareService()
    return service.compare(
        project_id=str(req.project_id),
        document_ids=[str(doc_id) for doc_id in req.document_ids],
        theme=req.theme,
    )
