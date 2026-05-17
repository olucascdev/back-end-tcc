"""
Endpoint para identificacao de lacunas de pesquisa.

POST /research/gaps — identifica lacunas de pesquisa em um projeto.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.domain.research_gap_service import ResearchGapService
from app.schemas.contracts_v1 import ResearchGapRequest, ResearchGapResponse

router = APIRouter()


@router.post(
    "/gaps",
    response_model=ResearchGapResponse,
    summary="Identificar lacunas de pesquisa",
    description="Analisa o corpus de documentos de um projeto e identifica lacunas de pesquisa com evidencias e perguntas sugeridas.",
)
def identify_research_gaps(request: ResearchGapRequest) -> ResearchGapResponse:
    """Identifica lacunas de pesquisa em um projeto.

    Recebe project_id e tema opcional, analisa os chunks disponiveis
    e retorna lacunas identificadas com evidencias e sugestoes.
    """
    service = ResearchGapService()
    return service.find_gaps(
        project_id=str(request.project_id),
        theme=request.theme,
    )
