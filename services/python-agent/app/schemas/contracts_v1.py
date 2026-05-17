"""
Contratos internos v1 entre servicos.

Define os schemas Pydantic usados na comunicacao entre o gateway Go
e o agente Python. Todos os campos seguem naming em ingles; comentarios
em PT-BR quando necessario.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Source – bloco de citacao usado em respostas de chat e comparacao
# ---------------------------------------------------------------------------


class Source(BaseModel):
    """Referencia a trecho de documento usado como fonte."""

    document: str
    page: int
    section: Optional[str] = None
    score: float
    source_type: Literal["project_document", "public_library"] = "project_document"


# ---------------------------------------------------------------------------
# ProcessDocument – processamento assincrono de documento
# ---------------------------------------------------------------------------


class ProcessDocumentRequest(BaseModel):
    """Requisicao para processar um documento recem-ingestado."""

    project_id: UUID
    document_id: UUID
    storage_key: str
    source_type: str = Field(default="user_upload")
    metadata: Optional[dict] = None


class ProcessDocumentResponse(BaseModel):
    """Resposta do agente apos aceitar/rejeitar o processamento."""

    document_id: UUID
    status: str = Field(pattern="^(pending|processing|ready|error)$")
    chunks_count: Optional[int] = None
    processed_at: Optional[datetime] = None
    error_message: Optional[str] = None


# ---------------------------------------------------------------------------
# Chat – interacao RAG com fontes
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    """Requisicao de chat com contexto RAG."""

    project_id: UUID
    session_id: str
    message: str
    filters: Optional[dict] = None
    retrieval_mode: str = Field(
        default="project_only",
        pattern="^(project_only|project_plus_public)$",
    )


class ChatResponse(BaseModel):
    """Resposta do chat com citacoes."""

    answer: str
    sources: list[Source]
    session_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ---------------------------------------------------------------------------
# Summarize – resumo estruturado de documento
# ---------------------------------------------------------------------------


class SummarizeRequest(BaseModel):
    """Requisicao de resumo de documento."""

    document_id: UUID
    project_id: UUID
    format: str = Field(default="structured")


class SummarizeResponse(BaseModel):
    """Resumo estruturado gerado pelo agente."""

    document_id: UUID
    summary: dict  # chaves esperadas: objective, methodology, results, conclusion
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ---------------------------------------------------------------------------
# Compare – comparacao tematica entre documentos
# ---------------------------------------------------------------------------


class CompareRequest(BaseModel):
    """Requisicao de comparacao entre dois ou mais documentos."""

    project_id: UUID
    document_ids: list[UUID] = Field(min_length=2)
    theme: str


class CompareResponse(BaseModel):
    """Resultado da comparacao tematica."""

    project_id: UUID
    comparison: dict
    sources: list[Source]
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ---------------------------------------------------------------------------
# ResearchGap – identificacao de lacunas de pesquisa
# ---------------------------------------------------------------------------


class ResearchGapRequest(BaseModel):
    """Requisicao para identificar lacunas de pesquisa em um projeto."""

    project_id: UUID
    theme: str = ""


class ResearchGapItem(BaseModel):
    """Uma lacuna de pesquisa identificada com evidencias e sugestoes."""

    gap_title: str
    why_gap: str
    evidence_sources: list[Source]
    suggested_questions: list[str]
    confidence: str = Field(pattern="^(low|medium|high)$")


class ResearchGapResponse(BaseModel):
    """Resposta com lacunas de pesquisa identificadas."""

    project_id: UUID
    gaps: list[ResearchGapItem]
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ---------------------------------------------------------------------------
# Webhook – notificacao de status de documento
# ---------------------------------------------------------------------------


class DocumentStatusWebhook(BaseModel):
    """Payload enviado ao gateway quando o status de um documento muda."""

    document_id: UUID
    project_id: UUID
    status: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    error_message: Optional[str] = None
    metadata: Optional[dict] = None
