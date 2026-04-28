"""
Endpoints de chat RAG.

Permite interacao com documentos processados usando retrieval-augmented generation.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.config import Settings
from app.domain.rag_service import LLMError, RAGService
from app.schemas.contracts_v1 import ChatRequest, ChatResponse

router = APIRouter()
logger = logging.getLogger(__name__)


def _get_settings() -> Settings:
    """Injeta configuracoes via Depends."""
    return Settings()


def _get_rag_service(
    settings: Annotated[Settings, Depends(_get_settings)],
) -> RAGService:
    """Injeta RAGService com dependencias configuradas."""
    return RAGService(settings=settings)


@router.post("", response_model=ChatResponse)
def chat(
    req: ChatRequest,
    request: Request,
    rag_service: Annotated[RAGService, Depends(_get_rag_service)],
) -> ChatResponse:
    """Responde pergunta usando contexto RAG.

    Busca chunks similares no pgvector, monta contexto e chama LLM
    para gerar resposta com citacoes de fontes.

    Se nao houver contexto relevante, retorna limitacao explicita.
    """
    request_id = getattr(request.state, "request_id", "unknown")
    logger.info(
        "Chat request: project_id=%s, session_id=%s, request_id=%s",
        req.project_id,
        req.session_id,
        request_id,
    )

    try:
        response = rag_service.chat(
            project_id=str(req.project_id),
            session_id=req.session_id,
            message=req.message,
        )
        return response
    except LLMError as exc:
        logger.error(
            "Erro ao gerar resposta LLM: %s, request_id=%s",
            exc,
            request_id,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Erro ao gerar resposta do modelo. Tente novamente.",
        ) from exc
    except Exception as exc:
        logger.error(
            "Erro inesperado no chat: %s, request_id=%s",
            exc,
            request_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao processar chat.",
        ) from exc
