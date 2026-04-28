"""
Endpoints de chat RAG.

Permite interacao com documentos processados usando retrieval-augmented generation.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas.contracts_v1 import ChatRequest, ChatResponse

router = APIRouter()


@router.post("", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    """Responde pergunta usando contexto RAG.

    Stub: retorna resposta mock com sources vazias.
    Implementacao real fara busca vetorial + LLM com citacoes.
    """
    return ChatResponse(
        answer="Esta e uma resposta mock do agente. A implementacao real fara busca vetorial nos embeddings do documento.",
        sources=[],
        session_id=req.session_id,
    )
