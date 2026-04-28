"""
Endpoints de resumo de documentos.

Gera resumos estruturados de documentos processados.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas.contracts_v1 import SummarizeRequest, SummarizeResponse

router = APIRouter()


@router.post("/summarize-document", response_model=SummarizeResponse)
def summarize_document(req: SummarizeRequest) -> SummarizeResponse:
    """Gera resumo estruturado de um documento.

    Stub: retorna summary mock com chaves esperadas.
    Implementacao real fara extracao de secoes via LLM.
    """
    return SummarizeResponse(
        document_id=req.document_id,
        summary={
            "objective": "Resumo mock do objetivo do documento.",
            "methodology": "Resumo mock da metodologia utilizada.",
            "results": "Resumo mock dos resultados encontrados.",
            "conclusion": "Resumo mock da conclusao do documento.",
        },
    )
