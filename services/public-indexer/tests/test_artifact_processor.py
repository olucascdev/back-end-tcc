"""
Testes do caso de uso ArtifactProcessorUseCase.

Verifica processamento de artefato, idempotencia e isolamento de falhas.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.application.artifact_processor import ArtifactProcessorUseCase
from app.domain.models import BookMetadata
from app.domain.services import BookCatalogService
from app.infrastructure.artifact_storage import ArtifactStorageService


@pytest.fixture
def mock_book_catalog() -> MagicMock:
    """Mock do servico de catalogo."""
    catalog = MagicMock(spec=BookCatalogService)
    catalog.find_by_stable_key = AsyncMock(return_value=None)
    catalog.update_artifact_ref = AsyncMock()
    catalog.mark_indexed = AsyncMock()
    return catalog


@pytest.fixture
def mock_artifact_storage() -> MagicMock:
    """Mock do servico de armazenamento."""
    storage = MagicMock(spec=ArtifactStorageService)
    storage.download_artifact = AsyncMock(return_value=b"Book content here")
    storage.store_artifact = MagicMock(return_value="gutenberg/42/v1.txt")
    storage.select_format = MagicMock(return_value="txt")
    return storage


@pytest.fixture
def processor(
    mock_book_catalog: MagicMock,
    mock_artifact_storage: MagicMock,
) -> ArtifactProcessorUseCase:
    """Caso de uso com mocks injetados."""
    return ArtifactProcessorUseCase(
        book_catalog=mock_book_catalog,
        artifact_storage=mock_artifact_storage,
    )


class TestArtifactProcessorSuccess:
    """Testes de processamento bem-sucedido."""

    @pytest.mark.asyncio
    async def test_process_gutenberg_book(
        self, processor: ArtifactProcessorUseCase
    ) -> None:
        """Verifica processamento de livro Gutenberg."""
        book = BookMetadata(
            gutenberg_id="42",
            title="Test Book",
            authors=["Author"],
        )

        result = await processor.execute(book)

        assert result.success is True
        assert result.artifact_key == "gutenberg/42/v1.txt"
        assert result.checksum is not None
        assert result.skipped is False

    @pytest.mark.asyncio
    async def test_process_updates_mongodb(
        self,
        processor: ArtifactProcessorUseCase,
        mock_book_catalog: MagicMock,
    ) -> None:
        """Verifica que referencia e atualizada no MongoDB."""
        book = BookMetadata(
            gutenberg_id="42",
            title="Test Book",
        )

        await processor.execute(book)

        mock_book_catalog.update_artifact_ref.assert_called_once()
        call_kwargs = mock_book_catalog.update_artifact_ref.call_args
        assert call_kwargs.kwargs["stable_key"] == "gutenberg:42"
        assert call_kwargs.kwargs["artifact_key"] == "gutenberg/42/v1.txt"

    @pytest.mark.asyncio
    async def test_process_computes_checksum(
        self,
        processor: ArtifactProcessorUseCase,
    ) -> None:
        """Verifica que checksum e computado corretamente."""
        book = BookMetadata(
            gutenberg_id="42",
            title="Test Book",
        )

        result = await processor.execute(book)

        # SHA-256 de b"Book content here"
        import hashlib

        expected = hashlib.sha256(b"Book content here").hexdigest()
        assert result.checksum == expected


class TestArtifactProcessorIdempotency:
    """Testes de idempotencia (checksum igual → skip)."""

    @pytest.mark.asyncio
    async def test_skip_when_checksum_unchanged(
        self,
        processor: ArtifactProcessorUseCase,
        mock_book_catalog: MagicMock,
        mock_artifact_storage: MagicMock,
    ) -> None:
        """Verifica que processamento e skipado se checksum igual."""
        import hashlib

        existing_checksum = hashlib.sha256(b"Book content here").hexdigest()
        mock_book_catalog.find_by_stable_key = AsyncMock(
            return_value={
                "stable_key": "gutenberg:42",
                "checksum": existing_checksum,
                "artifact_key": "gutenberg/42/v1.txt",
            }
        )

        book = BookMetadata(
            gutenberg_id="42",
            title="Test Book",
        )

        result = await processor.execute(book)

        assert result.success is True
        assert result.skipped is True
        # Nao deve chamar update_artifact_ref
        mock_book_catalog.update_artifact_ref.assert_not_called()
        # Nao deve chamar store_artifact
        mock_artifact_storage.store_artifact.assert_not_called()


class TestArtifactProcessorFailure:
    """Testes de isolamento de falhas."""

    @pytest.mark.asyncio
    async def test_download_failure_isolated(
        self,
        processor: ArtifactProcessorUseCase,
        mock_artifact_storage: MagicMock,
    ) -> None:
        """Verifica que falha de download nao quebra o fluxo."""
        mock_artifact_storage.download_artifact = AsyncMock(
            side_effect=RuntimeError("Download failed")
        )

        book = BookMetadata(
            gutenberg_id="42",
            title="Test Book",
        )

        result = await processor.execute(book)

        assert result.success is False
        assert result.error == "Download failed"
        assert result.artifact_key is None

    @pytest.mark.asyncio
    async def test_minio_failure_isolated(
        self,
        processor: ArtifactProcessorUseCase,
        mock_artifact_storage: MagicMock,
    ) -> None:
        """Verifica que falha do MinIO nao quebra o fluxo."""
        mock_artifact_storage.store_artifact = MagicMock(
            side_effect=RuntimeError("MinIO unavailable")
        )

        book = BookMetadata(
            gutenberg_id="42",
            title="Test Book",
        )

        result = await processor.execute(book)

        assert result.success is False
        assert "MinIO unavailable" in result.error

    @pytest.mark.asyncio
    async def test_no_download_url(self, processor: ArtifactProcessorUseCase) -> None:
        """Verifica que livro sem URL de download retorna erro."""
        book = BookMetadata(
            title="No ID Book",
            authors=["Author"],
            # Sem gutenberg_id e sem ol_key
        )

        result = await processor.execute(book)

        assert result.success is False
        assert "Nenhuma URL de download disponivel" in result.error


class TestArtifactProcessorOpenLibrary:
    """Testes de processamento de livro Open Library."""

    @pytest.mark.asyncio
    async def test_process_openlibrary_book(
        self, processor: ArtifactProcessorUseCase
    ) -> None:
        """Verifica processamento de livro Open Library."""
        book = BookMetadata(
            ol_key="/works/OL123W",
            title="OL Book",
            authors=["OL Author"],
        )

        result = await processor.execute(book)

        assert result.success is True
        # URL deve ser construida com o OL ID
        mock_artifact_storage = processor._artifact_storage
        mock_artifact_storage.download_artifact.assert_called_once()
        call_args = mock_artifact_storage.download_artifact.call_args
        assert "OL123W" in call_args.args[0]


class TestArtifactProcessorScientificSources:
    """Testes de processamento de fontes cientificas."""

    @pytest.mark.asyncio
    async def test_process_openalex_book(
        self, processor: ArtifactProcessorUseCase
    ) -> None:
        """Verifica processamento de trabalho OpenAlex."""
        book = BookMetadata(
            source_id="W123456",
            source_provider="openalex",
            title="OpenAlex Paper",
            authors=["Author A"],
            url="https://example.com/paper.pdf",
        )

        result = await processor.execute(book)

        assert result.success is True
        mock_artifact_storage = processor._artifact_storage
        mock_artifact_storage.download_artifact.assert_called_once()
        call_args = mock_artifact_storage.download_artifact.call_args
        assert call_args.args[0] == "https://example.com/paper.pdf"

    @pytest.mark.asyncio
    async def test_process_arxiv_book(
        self, processor: ArtifactProcessorUseCase
    ) -> None:
        """Verifica processamento de artigo arXiv."""
        book = BookMetadata(
            source_id="2101.12345",
            source_provider="arxiv",
            title="arXiv Paper",
            authors=["Author B"],
        )

        result = await processor.execute(book)

        assert result.success is True
        mock_artifact_storage = processor._artifact_storage
        mock_artifact_storage.download_artifact.assert_called_once()
        call_args = mock_artifact_storage.download_artifact.call_args
        assert call_args.args[0] == "https://arxiv.org/pdf/2101.12345.pdf"

    @pytest.mark.asyncio
    async def test_process_crossref_book_with_url(
        self, processor: ArtifactProcessorUseCase
    ) -> None:
        """Verifica processamento de trabalho Crossref com URL."""
        book = BookMetadata(
            source_id="10.1000/test",
            source_provider="crossref",
            title="Crossref Paper",
            authors=["Author C"],
            url="https://example.com/crossref.pdf",
        )

        result = await processor.execute(book)

        assert result.success is True
        mock_artifact_storage = processor._artifact_storage
        mock_artifact_storage.download_artifact.assert_called_once()
        call_args = mock_artifact_storage.download_artifact.call_args
        assert call_args.args[0] == "https://example.com/crossref.pdf"

    @pytest.mark.asyncio
    async def test_process_crossref_book_without_url(
        self, processor: ArtifactProcessorUseCase
    ) -> None:
        """Verifica que Crossref sem URL retorna erro."""
        book = BookMetadata(
            source_id="10.1000/nourl",
            source_provider="crossref",
            title="Crossref Paper No URL",
            authors=["Author D"],
        )

        result = await processor.execute(book)

        assert result.success is False
        assert "Nenhuma URL de download disponivel" in result.error
