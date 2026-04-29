"""
Caso de uso para processamento de artefatos de livros.

Coordena download, checksum, armazenamento no MinIO
e atualizacao da referencia no MongoDB.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from app.domain.models import BookMetadata
from app.domain.services import BookCatalogService
from app.infrastructure.artifact_storage import ArtifactStorageService

logger = logging.getLogger(__name__)


@dataclass
class ArtifactProcessResult:
    """Resultado do processamento de um artefato."""

    stable_key: str
    success: bool
    artifact_key: Optional[str] = None
    checksum: Optional[str] = None
    error: Optional[str] = None
    skipped: bool = False


class ArtifactProcessorUseCase:
    """
    Caso de uso para processar artefato de um livro.

    Fluxo:
    1. Determina URL de download a partir dos formatos disponiveis
    2. Baixa artefato
    3. Computa checksum
    4. Verifica idempotencia (checksum igual → skip)
    5. Armazena no MinIO
    6. Atualiza referencia no MongoDB
    """

    def __init__(
        self,
        book_catalog: BookCatalogService,
        artifact_storage: ArtifactStorageService,
    ) -> None:
        self._book_catalog = book_catalog
        self._artifact_storage = artifact_storage

    async def execute(self, book: BookMetadata) -> ArtifactProcessResult:
        """
        Processa artefato de um livro.

        Args:
            book: metadados do livro com informacoes de formato.

        Returns:
            Resultado do processamento.
        """
        stable_key = book.stable_key()

        try:
            # Verifica se ja existe no catalogo com checksum
            existing = await self._book_catalog.find_by_stable_key(stable_key)

            # Se ja tem checksum e artefato, verifica idempotencia
            # (sera verificado apos download do conteudo)

            # Determina formato e URL de download
            # Para Gutenberg, as URLs vem do client; para Open Library,
            # precisamos construir a URL de download
            download_url = self._resolve_download_url(book)
            if not download_url:
                return ArtifactProcessResult(
                    stable_key=stable_key,
                    success=False,
                    error="Nenhuma URL de download disponivel",
                )

            # Baixa artefato
            content = await self._artifact_storage.download_artifact(download_url)

            # Computa checksum
            checksum = ArtifactStorageService.compute_checksum(content)

            # Verifica idempotencia: se checksum igual ao existente, skip
            if existing and existing.get("checksum") == checksum:
                logger.info(
                    "Artefato inalterado, skip: stable_key=%s",
                    stable_key,
                )
                return ArtifactProcessResult(
                    stable_key=stable_key,
                    success=True,
                    artifact_key=existing.get("artifact_key"),
                    checksum=checksum,
                    skipped=True,
                )

            # Seleciona formato para armazenamento
            fmt = self._resolve_format(book)
            if not fmt:
                fmt = "txt"  # Fallback

            # Armazena no MinIO
            artifact_key = self._artifact_storage.store_artifact(
                stable_key=stable_key,
                content=content,
                fmt=fmt,
            )

            # Atualiza referencia no MongoDB
            await self._book_catalog.update_artifact_ref(
                stable_key=stable_key,
                artifact_key=artifact_key,
                checksum=checksum,
            )

            logger.info(
                "Artefato processado: stable_key=%s, artifact_key=%s",
                stable_key,
                artifact_key,
            )

            return ArtifactProcessResult(
                stable_key=stable_key,
                success=True,
                artifact_key=artifact_key,
                checksum=checksum,
            )

        except Exception as exc:
            logger.error(
                "Falha ao processar artefato: stable_key=%s, erro=%s",
                stable_key,
                exc,
            )
            return ArtifactProcessResult(
                stable_key=stable_key,
                success=False,
                error=str(exc),
            )

    def _resolve_download_url(self, book: BookMetadata) -> Optional[str]:
        """
        Resolve URL de download a partir dos metadados do livro.

        Para Gutenberg: usa download_urls se disponivel, senao constroi URL.
        Para Open Library: constroi URL de download do archive.org.

        Args:
            book: metadados do livro.

        Returns:
            URL de download ou None.
        """
        # Se tem gutenberg_id, constroi URL padrao do Gutenberg
        if book.gutenberg_id:
            fmt = self._resolve_format(book) or "txt"
            return f"https://www.gutenberg.org/ebooks/{book.gutenberg_id}.{fmt}"

        # Se tem ol_key, constroi URL do archive.org
        if book.ol_key:
            # ol_key vem como /works/OL123W, extrai ID
            ol_id = book.ol_key.split("/")[-1]  # OL123W
            return f"https://archive.org/download/{ol_id}/{ol_id}.txt"

        return None

    def _resolve_format(self, book: BookMetadata) -> Optional[str]:
        """
        Resolve formato preferido a partir dos metadados.

        Args:
            book: metadados do livro.

        Returns:
            Formato selecionado ou None.
        """
        # Para Gutenberg, os formatos podem estar nos subjects ou inferidos
        # Para simplificar, usa a prioridade configurada
        available = ["txt", "epub", "pdf"]  # Formatos padrao disponiveis
        return self._artifact_storage.select_format(available)
