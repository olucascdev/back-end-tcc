"""
Modelos de dominio para o public-indexer.

Define entidades e value objects usados na logica de indexacao.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    """Status possiveis de um job de indexacao."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class IndexerJob(BaseModel):
    """
    Representa um job de indexacao de acervo publico.

    Atributos:
        job_id: identificador unico do job.
        status: estado atual do job.
        source_filter: filtro opcional de fonte (ex: 'gutenberg', 'openlibrary').
        dry_run: se True, apenas simula sem persistir.
        created_at: timestamp de criacao.
        started_at: timestamp de inicio da execucao.
        completed_at: timestamp de conclusao.
        error_message: mensagem de erro se falhou.
        items_processed: contador de itens processados.
    """

    job_id: UUID = Field(default_factory=uuid4)
    status: JobStatus = JobStatus.PENDING
    source_filter: Optional[str] = None
    dry_run: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    items_processed: int = 0

    def mark_running(self) -> None:
        """Transiciona job para running."""
        self.status = JobStatus.RUNNING
        self.started_at = datetime.now(UTC)

    def mark_completed(self, items_processed: int = 0) -> None:
        """Transiciona job para completed."""
        self.status = JobStatus.COMPLETED
        self.completed_at = datetime.now(UTC)
        self.items_processed = items_processed

    def mark_failed(self, error: str) -> None:
        """Transiciona job para failed."""
        self.status = JobStatus.FAILED
        self.completed_at = datetime.now(UTC)
        self.error_message = error


class BookMetadata(BaseModel):
    """
    Metadados de livro do catalogo publico.

    Atributos:
        gutenberg_id: ID do Project Gutenberg (se aplicavel).
        ol_key: chave Open Library (ex: /works/OL123W).
        title: titulo do livro.
        authors: lista de autores.
        language: idioma principal.
        subjects: lista de assuntos/categorias.
        year: ano de publicacao.
        checksum: hash do artefato para deduplicacao.
    """

    gutenberg_id: Optional[str] = None
    ol_key: Optional[str] = None
    title: str
    authors: list[str] = Field(default_factory=list)
    language: Optional[str] = None
    subjects: list[str] = Field(default_factory=list)
    year: Optional[int] = None
    checksum: Optional[str] = None

    def stable_key(self) -> str:
        """
        Gera chave estavel para deduplicacao.

        Prioridade: gutenberg_id > ol_key > hash(title+authors).
        """
        if self.gutenberg_id:
            return f"gutenberg:{self.gutenberg_id}"
        if self.ol_key:
            return f"ol:{self.ol_key}"
        # Fallback: hash de titulo + autores
        import hashlib

        raw = f"{self.title}|{'|'.join(sorted(self.authors))}"
        return f"hash:{hashlib.sha256(raw.encode()).hexdigest()[:16]}"


class EmbeddingMetadata(BaseModel):
    """
    Contrato de metadata para embeddings publicos no JSONB.

    Campos obrigatorios conforme especificacao da plataforma.
    """

    source_type: str = Field(
        default="public_library",
        description="Tipo de origem (ex: public_library, user_upload)",
    )
    source_provider: str = Field(
        description="Provedor da fonte (ex: gutenberg, openlibrary, google_books)"
    )
    source_id: str = Field(description="Identificador unico na fonte original")
    artifact_key: str = Field(description="Chave do artefato no MinIO/S3")
    checksum: str = Field(description="Hash do conteudo para integridade")
    chunk_version: int = Field(
        default=1, description="Versao do chunk para reprocessamento"
    )

    def to_dict(self) -> dict:
        """Converte para dict compativel com JSONB."""
        return self.model_dump()
