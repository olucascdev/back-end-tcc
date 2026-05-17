"""
Processamento de embeddings para livros do acervo publico.

Orquestra extracao de texto, chunking, geracao de embeddings
e armazenamento no vector store PostgreSQL.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from app.domain.models import BookMetadata, EmbeddingMetadata
from app.infrastructure.artifact_storage import ArtifactStorageService
from app.infrastructure.chunking import TextChunker
from app.infrastructure.embedder import OpenAIEmbedder
from app.infrastructure.text_extraction import TextExtractor
from app.infrastructure.vector_store import PublicVectorStore

logger = logging.getLogger(__name__)

CHUNK_VERSION = 1


@dataclass
class EmbeddingProcessResult:
    """Resultado do processamento de embeddings de um livro."""

    stable_key: str
    success: bool
    chunks_count: int = 0
    skipped: bool = False
    error: Optional[str] = None


class EmbeddingProcessorUseCase:
    """
    Caso de uso para gerar e armazenar embeddings de um livro.

    Fluxo:
    1. Baixa artefato do MinIO
    2. Extrai texto
    3. Divide em chunks
    4. Verifica idempotencia (fingerprint)
    5. Gera embeddings
    6. Armazena no vector store
    7. Atualiza MongoDB com contagem
    """

    def __init__(
        self,
        artifact_storage: ArtifactStorageService,
        text_extractor: TextExtractor,
        text_chunker: TextChunker,
        embedder: OpenAIEmbedder,
        vector_store: PublicVectorStore,
        book_catalog,  # BookCatalogService (injected)
    ) -> None:
        """
        Inicializa processador de embeddings.

        Args:
            artifact_storage: servico de armazenamento de artefatos.
            text_extractor: extrator de texto.
            text_chunker: divisor de texto em chunks.
            embedder: gerador de embeddings.
            vector_store: armazenamento de vetores.
            book_catalog: servico de catalogo para atualizacao.
        """
        self._artifact_storage = artifact_storage
        self._text_extractor = text_extractor
        self._text_chunker = text_chunker
        self._embedder = embedder
        self._vector_store = vector_store
        self._book_catalog = book_catalog

    async def execute(
        self,
        book: BookMetadata,
        artifact_key: str,
        checksum: str,
    ) -> EmbeddingProcessResult:
        """
        Processa embeddings de um livro.

        Args:
            book: metadados do livro.
            artifact_key: chave do artefato no MinIO.
            checksum: hash do conteudo do artefato.

        Returns:
            Resultado do processamento.
        """
        stable_key = book.stable_key()
        source_provider = self._extract_provider(stable_key)
        source_id = self._extract_source_id(stable_key)

        try:
            # Determina formato do artefato
            fmt = artifact_key.rsplit(".", 1)[-1] if "." in artifact_key else "txt"

            # Passo 1: Baixa artefato do MinIO
            logger.info(
                "Baixando artefato para embedding: key=%s",
                artifact_key,
                extra={
                    "job_id": "",
                    "source_provider": source_provider,
                    "stage": "artifact_download",
                },
            )
            content = self._artifact_storage.get_artifact(artifact_key)

            # Passo 2: Extrai texto
            logger.info(
                "Extraindo texto: key=%s, format=%s",
                artifact_key,
                fmt,
                extra={
                    "job_id": "",
                    "source_provider": source_provider,
                    "stage": "text_extraction",
                },
            )
            text = self._text_extractor.extract(artifact_key, content, fmt)

            if not text or not text.strip():
                return EmbeddingProcessResult(
                    stable_key=stable_key,
                    success=False,
                    error="Texto vazio apos extracao",
                )

            # Passo 3: Divide em chunks
            logger.info(
                "Chunking texto: len=%d",
                len(text),
                extra={
                    "job_id": "",
                    "source_provider": source_provider,
                    "stage": "chunking",
                },
            )
            chunks = self._text_chunker.chunk(text)

            if not chunks:
                return EmbeddingProcessResult(
                    stable_key=stable_key,
                    success=False,
                    error="Nenhum chunk gerado",
                )

            # Passo 4: Verifica idempotencia
            fingerprint_exists = await self._vector_store.check_existing_fingerprint(
                source_id=source_id,
                checksum=checksum,
                chunk_version=CHUNK_VERSION,
            )

            if fingerprint_exists:
                logger.info(
                    "Embeddings ja existem (fingerprint): stable_key=%s",
                    stable_key,
                )
                return EmbeddingProcessResult(
                    stable_key=stable_key,
                    success=True,
                    chunks_count=0,
                    skipped=True,
                )

            # Limpa embeddings obsoletos se checksum mudou
            existing_doc = await self._book_catalog.find_by_stable_key(stable_key)
            if existing_doc:
                old_checksum = existing_doc.get("checksum")
                if old_checksum and old_checksum != checksum:
                    deleted = await self._vector_store.delete_by_fingerprint(
                        source_id, old_checksum
                    )
                    logger.info(
                        "Embeddings obsoletos removidos: stable_key=%s, old_checksum=%s, deleted=%d",
                        stable_key,
                        old_checksum[:8],
                        deleted,
                    )

            # Passo 5: Gera embeddings
            logger.info(
                "Gerando embeddings: chunks=%d",
                len(chunks),
                extra={
                    "job_id": "",
                    "source_provider": source_provider,
                    "stage": "embedding",
                },
            )
            chunk_texts = [chunk.text for chunk in chunks]
            embeddings = await self._embedder.embed_texts(chunk_texts)

            # Passo 6: Constroi registros para vector store
            records = []
            for chunk, embedding in zip(chunks, embeddings):
                metadata = EmbeddingMetadata(
                    source_type="public_library",
                    source_provider=source_provider,
                    source_id=source_id,
                    artifact_key=artifact_key,
                    checksum=checksum,
                    chunk_version=CHUNK_VERSION,
                )

                records.append(
                    {
                        "content": chunk.text,
                        "embedding": embedding,
                        "metadata": metadata.to_dict(),
                    }
                )

            # Passo 7: Insere no vector store
            logger.info(
                "Inserindo embeddings no vector store: count=%d",
                len(records),
                extra={
                    "job_id": "",
                    "source_provider": source_provider,
                    "stage": "vector_store_write",
                },
            )
            inserted = await self._vector_store.insert_embeddings(records)

            # Passo 8: Atualiza MongoDB com contagem
            logger.info(
                "Atualizando MongoDB com embedding_count: stable_key=%s",
                stable_key,
                extra={
                    "job_id": "",
                    "source_provider": source_provider,
                    "stage": "mongo_update",
                },
            )
            await self._book_catalog.update_embedding_count(
                stable_key=stable_key,
                embedding_count=inserted,
            )

            logger.info(
                "Embeddings processados com sucesso: stable_key=%s, chunks=%d",
                stable_key,
                inserted,
            )

            return EmbeddingProcessResult(
                stable_key=stable_key,
                success=True,
                chunks_count=inserted,
            )

        except Exception as exc:
            logger.error(
                "Falha no processamento de embeddings: stable_key=%s, error=%s",
                stable_key,
                exc,
            )
            return EmbeddingProcessResult(
                stable_key=stable_key,
                success=False,
                error=str(exc),
            )

    @staticmethod
    def _extract_provider(stable_key: str) -> str:
        """Extrai provider do stable_key (ex: 'gutenberg' de 'gutenberg:123')."""
        if ":" in stable_key:
            return stable_key.split(":")[0]
        return "unknown"

    @staticmethod
    def _extract_source_id(stable_key: str) -> str:
        """Extrai source_id do stable_key (ex: '123' de 'gutenberg:123')."""
        if ":" in stable_key:
            return stable_key.split(":", 1)[1]
        return stable_key
