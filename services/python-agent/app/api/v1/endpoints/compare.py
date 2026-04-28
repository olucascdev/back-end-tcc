"""
Endpoints de comparacao de documentos.

Compara dois ou mais documentos sob um tema especifico.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas.contracts_v1 import CompareRequest, CompareResponse

router = APIRouter()


@router.post("/compare-documents", response_model=CompareResponse)
def compare_documents(req: CompareRequest) -> CompareResponse:
    """Compara documentos sob um tema especifico.

    Stub: retorna comparacao mock com sources vazias.
    Implementacao real fara analise tematica cruzada via LLM.
    """
    return CompareResponse(
        project_id=req.project_id,
        comparison={
            "theme": req.theme,
            "similarities": "Pontos em comum mock entre os documentos.",
            "differences": "Diferencas mock entre os documentos.",
            "synthesis": "Sintese mock da comparacao tematica.",
        },
        sources=[],
    )
