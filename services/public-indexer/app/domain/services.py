"""
Servicos de dominio para o public-indexer.

Contem logica de negocio pura: BookCatalogService para interacao
com MongoDB e gerenciamento de jobs.
"""

from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from app.domain.models import BookMetadata, IndexerJob, JobStatus

logger = logging.getLogger(__name__)


class BookCatalogService:
    """
    Servico de catalogo de livros publicos.

    Responsavel por buscar, persistir e deduplicar livros no MongoDB.
    """

    def __init__(self, mongo_db) -> None:
        """
        Inicializa com referencia ao database MongoDB.

        Args:
            mongo_db: instancia motor database (injetada via infra).
        """
        self._db = mongo_db
        self._collection = mongo_db.get_collection("books")

    async def find_by_stable_key(self, stable_key: str) -> Optional[dict]:
        """
        Busca livro por chave estavel no MongoDB.

        Args:
            stable_key: chave gerada por BookMetadata.stable_key().

        Returns:
            Documento do livro ou None se nao encontrado.
        """
        return await self._collection.find_one({"stable_key": stable_key})

    async def upsert_book(self, book: BookMetadata) -> dict:
        """
        Insere ou atualiza livro no catalogo.

        Usa stable_key para deduplicacao.

        Args:
            book: metadados do livro.

        Returns:
            Documento persistido com _id do MongoDB.
        """
        stable_key = book.stable_key()
        doc = book.model_dump()
        doc["stable_key"] = stable_key

        result = await self._collection.update_one(
            {"stable_key": stable_key},
            {"$set": doc, "$setOnInsert": {"indexed": False, "indexed_at": None}},
            upsert=True,
        )

        logger.info(
            "Livro upserted: stable_key=%s, modified=%s, upserted=%s",
            stable_key,
            result.modified_count,
            result.upserted_id,
        )
        return {"stable_key": stable_key, "modified": result.modified_count > 0}

    async def get_pending_books(
        self,
        limit: int = 100,
        source_filter: Optional[str] = None,
    ) -> list[dict]:
        """
        Retorna livros pendentes de indexacao.

        Args:
            limit: numero maximo de registros.
            source_filter: provider opcional para filtrar pendencias
                (ex: openalex, arxiv, crossref, gutenberg, openlibrary).

        Returns:
            Lista de documentos MongoDB pendentes.
        """
        query: dict = {"indexed": False}
        if source_filter:
            query["source_provider"] = source_filter

        cursor = self._collection.find(query).limit(limit)
        return await cursor.to_list(length=limit)

    async def mark_indexed(self, stable_key: str) -> None:
        """
        Marca livro como indexado.

        Args:
            stable_key: chave estavel do livro.
        """
        from datetime import UTC, datetime

        await self._collection.update_one(
            {"stable_key": stable_key},
            {"$set": {"indexed": True, "indexed_at": datetime.now(UTC)}},
        )

    async def update_artifact_ref(
        self,
        stable_key: str,
        artifact_key: str,
        checksum: str,
    ) -> None:
        """
        Atualiza referencia de artefato e checksum no documento do livro.

        Args:
            stable_key: chave estavel do livro.
            artifact_key: chave do artefato no MinIO.
            checksum: hash SHA-256 do conteudo.
        """
        from datetime import UTC, datetime

        await self._collection.update_one(
            {"stable_key": stable_key},
            {
                "$set": {
                    "artifact_key": artifact_key,
                    "checksum": checksum,
                    "artifact_updated_at": datetime.now(UTC),
                }
            },
        )

    async def update_embedding_count(
        self,
        stable_key: str,
        embedding_count: int,
    ) -> None:
        """
        Atualiza contagem de embeddings no documento do livro.

        Args:
            stable_key: chave estavel do livro.
            embedding_count: numero de chunks/embeddings gerados.
        """
        from datetime import UTC, datetime

        await self._collection.update_one(
            {"stable_key": stable_key},
            {
                "$set": {
                    "embedding_count": embedding_count,
                    "embeddings_updated_at": datetime.now(UTC),
                }
            },
        )


class JobStore:
    """
    Armazenamento in-memory de jobs de indexacao.

    Em producao, usar Redis ou PostgreSQL para persistencia.
    """

    def __init__(self) -> None:
        self._jobs: dict[UUID, IndexerJob] = {}

    def create(self, job: IndexerJob) -> IndexerJob:
        """Registra novo job."""
        self._jobs[job.job_id] = job
        logger.info("Job criado: job_id=%s", job.job_id)
        return job

    def get(self, job_id: UUID) -> Optional[IndexerJob]:
        """Retorna job por ID."""
        return self._jobs.get(job_id)

    def update(self, job: IndexerJob) -> None:
        """Atualiza job existente."""
        self._jobs[job.job_id] = job

    def list_all(self) -> list[IndexerJob]:
        """Lista todos os jobs."""
        return list(self._jobs.values())
