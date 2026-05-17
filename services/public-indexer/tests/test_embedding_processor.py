"""
Testes do EmbeddingProcessorUseCase.

Verifica fluxo completo de processamento de embeddings,
idempotencia e isolamento de falhas.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.application.embedding_processor import EmbeddingProcessorUseCase
from app.domain.models import BookMetadata


@pytest.fixture
def mock_artifact_storage() -> MagicMock:
    """Mock do servico de armazenamento."""
    storage = MagicMock()
    storage.get_artifact = MagicMock(return_value=b"Book content here")
    return storage


@pytest.fixture
def mock_text_extractor() -> MagicMock:
    """Mock do extrator de texto."""
    extractor = MagicMock()
    extractor.extract = MagicMock(return_value="This is extracted text content. " * 20)
    return extractor


@pytest.fixture
def mock_text_chunker() -> MagicMock:
    """Mock do chunker."""
    from app.infrastructure.chunking import TextChunk

    chunker = MagicMock()
    chunks = [
        TextChunk(
            text=f"Chunk {i} content",
            chunk_index=i,
            char_start=i * 10,
            char_end=(i + 1) * 10,
        )
        for i in range(3)
    ]
    chunker.chunk = MagicMock(return_value=chunks)
    return chunker


@pytest.fixture
def mock_embedder() -> MagicMock:
    """Mock do embedder."""
    embedder = MagicMock()
    embedder.embed_texts = AsyncMock(return_value=[[0.1] * 1536 for _ in range(3)])
    return embedder


@pytest.fixture
def mock_vector_store() -> MagicMock:
    """Mock do vector store."""
    store = MagicMock()
    store.check_existing_fingerprint = AsyncMock(return_value=False)
    store.insert_embeddings = AsyncMock(return_value=3)
    store.delete_by_fingerprint = AsyncMock(return_value=1)
    return store


@pytest.fixture
def mock_book_catalog() -> MagicMock:
    """Mock do catalogo de livros."""
    catalog = MagicMock()
    catalog.update_embedding_count = AsyncMock()
    catalog.find_by_stable_key = AsyncMock(return_value=None)
    return catalog


@pytest.fixture
def processor(
    mock_artifact_storage: MagicMock,
    mock_text_extractor: MagicMock,
    mock_text_chunker: MagicMock,
    mock_embedder: MagicMock,
    mock_vector_store: MagicMock,
    mock_book_catalog: MagicMock,
) -> EmbeddingProcessorUseCase:
    """Processador com mocks injetados."""
    return EmbeddingProcessorUseCase(
        artifact_storage=mock_artifact_storage,
        text_extractor=mock_text_extractor,
        text_chunker=mock_text_chunker,
        embedder=mock_embedder,
        vector_store=mock_vector_store,
        book_catalog=mock_book_catalog,
    )


class TestEmbeddingProcessorSuccess:
    """Testes de processamento bem-sucedido."""

    @pytest.mark.asyncio
    async def test_process_book_embeddings(
        self, processor: EmbeddingProcessorUseCase
    ) -> None:
        """Verifica processamento completo de embeddings."""
        book = BookMetadata(
            gutenberg_id="42",
            title="Test Book",
            authors=["Author"],
        )

        result = await processor.execute(
            book=book,
            artifact_key="gutenberg/42/v1.txt",
            checksum="abc123",
        )

        assert result.success is True
        assert result.chunks_count == 3
        assert result.skipped is False
        assert result.error is None

    @pytest.mark.asyncio
    async def test_updates_mongodb_embedding_count(
        self,
        processor: EmbeddingProcessorUseCase,
        mock_book_catalog: MagicMock,
    ) -> None:
        """Verifica que MongoDB e atualizado com contagem."""
        book = BookMetadata(gutenberg_id="42", title="Test")

        await processor.execute(
            book=book,
            artifact_key="gutenberg/42/v1.txt",
            checksum="abc123",
        )

        mock_book_catalog.update_embedding_count.assert_called_once()
        call_kwargs = mock_book_catalog.update_embedding_count.call_args
        assert call_kwargs.kwargs["stable_key"] == "gutenberg:42"
        assert call_kwargs.kwargs["embedding_count"] == 3


class TestEmbeddingProcessorIdempotency:
    """Testes de idempotencia."""

    @pytest.mark.asyncio
    async def test_skip_when_fingerprint_exists(
        self,
        processor: EmbeddingProcessorUseCase,
        mock_vector_store: MagicMock,
    ) -> None:
        """Verifica que processamento e skipado se fingerprint existe."""
        mock_vector_store.check_existing_fingerprint = AsyncMock(return_value=True)

        book = BookMetadata(gutenberg_id="42", title="Test")

        result = await processor.execute(
            book=book,
            artifact_key="gutenberg/42/v1.txt",
            checksum="abc123",
        )

        assert result.success is True
        assert result.skipped is True
        assert result.chunks_count == 0
        # Nao deve chamar embedder ou vector store
        mock_vector_store.insert_embeddings.assert_not_called()


class TestEmbeddingProcessorFailure:
    """Testes de isolamento de falhas."""

    @pytest.mark.asyncio
    async def test_empty_text_after_extraction(
        self,
        processor: EmbeddingProcessorUseCase,
        mock_text_extractor: MagicMock,
    ) -> None:
        """Verifica falha quando texto extraido e vazio."""
        mock_text_extractor.extract = MagicMock(return_value="")

        book = BookMetadata(gutenberg_id="42", title="Test")

        result = await processor.execute(
            book=book,
            artifact_key="gutenberg/42/v1.txt",
            checksum="abc123",
        )

        assert result.success is False
        assert "Texto vazio" in result.error

    @pytest.mark.asyncio
    async def test_no_chunks_generated(
        self,
        processor: EmbeddingProcessorUseCase,
        mock_text_chunker: MagicMock,
    ) -> None:
        """Verifica falha quando nenhum chunk e gerado."""
        mock_text_chunker.chunk = MagicMock(return_value=[])

        book = BookMetadata(gutenberg_id="42", title="Test")

        result = await processor.execute(
            book=book,
            artifact_key="gutenberg/42/v1.txt",
            checksum="abc123",
        )

        assert result.success is False
        assert "Nenhum chunk" in result.error

    @pytest.mark.asyncio
    async def test_embedding_generation_failure(
        self,
        processor: EmbeddingProcessorUseCase,
        mock_embedder: MagicMock,
    ) -> None:
        """Verifica falha na geracao de embeddings."""
        mock_embedder.embed_texts = AsyncMock(side_effect=RuntimeError("API error"))

        book = BookMetadata(gutenberg_id="42", title="Test")

        result = await processor.execute(
            book=book,
            artifact_key="gutenberg/42/v1.txt",
            checksum="abc123",
        )

        assert result.success is False
        assert "API error" in result.error

    @pytest.mark.asyncio
    async def test_vector_store_write_failure(
        self,
        processor: EmbeddingProcessorUseCase,
        mock_vector_store: MagicMock,
    ) -> None:
        """Verifica falha na escrita do vector store."""
        mock_vector_store.insert_embeddings = AsyncMock(
            side_effect=RuntimeError("DB error")
        )

        book = BookMetadata(gutenberg_id="42", title="Test")

        result = await processor.execute(
            book=book,
            artifact_key="gutenberg/42/v1.txt",
            checksum="abc123",
        )

        assert result.success is False
        assert "DB error" in result.error


class TestEmbeddingProcessorProviderExtraction:
    """Testes de extracao de provider e source_id."""

    @pytest.mark.asyncio
    async def test_gutenberg_provider(
        self, processor: EmbeddingProcessorUseCase
    ) -> None:
        """Verifica extracao de provider Gutenberg."""
        book = BookMetadata(gutenberg_id="42", title="Test")
        result = await processor.execute(
            book=book,
            artifact_key="gutenberg/42/v1.txt",
            checksum="abc123",
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_openlibrary_provider(
        self, processor: EmbeddingProcessorUseCase
    ) -> None:
        """Verifica extracao de provider Open Library."""
        book = BookMetadata(ol_key="/works/OL123W", title="Test")
        result = await processor.execute(
            book=book,
            artifact_key="openlibrary/OL123W/v1.txt",
            checksum="abc123",
        )
        assert result.success is True


class TestEmbeddingProcessorReindex:
    """Testes do caminho de reindexacao por mudanca de checksum."""

    @pytest.mark.asyncio
    async def test_delete_old_embeddings_on_checksum_change(
        self,
        processor: EmbeddingProcessorUseCase,
        mock_vector_store: MagicMock,
        mock_book_catalog: MagicMock,
    ) -> None:
        """Verifica que embeddings antigos sao removidos quando checksum muda."""
        # Simula documento existente com checksum antigo
        mock_book_catalog.find_by_stable_key = AsyncMock(
            return_value={"checksum": "old_checksum_123"}
        )

        book = BookMetadata(gutenberg_id="42", title="Test Book")

        result = await processor.execute(
            book=book,
            artifact_key="gutenberg/42/v1.txt",
            checksum="new_checksum_456",
        )

        # Verifica que delete foi chamado com source_id e checksum antigo
        mock_vector_store.delete_by_fingerprint.assert_called_once_with(
            "42", "old_checksum_123"
        )
        # Verifica que insert ainda foi chamado apos limpeza
        mock_vector_store.insert_embeddings.assert_called_once()
        assert result.success is True
        assert result.skipped is False

    @pytest.mark.asyncio
    async def test_no_delete_when_checksum_unchanged(
        self,
        processor: EmbeddingProcessorUseCase,
        mock_vector_store: MagicMock,
        mock_book_catalog: MagicMock,
    ) -> None:
        """Verifica que nao ha delete quando checksum e igual."""
        mock_book_catalog.find_by_stable_key = AsyncMock(
            return_value={"checksum": "same_checksum"}
        )

        book = BookMetadata(gutenberg_id="42", title="Test Book")

        result = await processor.execute(
            book=book,
            artifact_key="gutenberg/42/v1.txt",
            checksum="same_checksum",
        )

        # Nao deve chamar delete pois checksum nao mudou
        mock_vector_store.delete_by_fingerprint.assert_not_called()
        # Insert deve ser chamado normalmente
        mock_vector_store.insert_embeddings.assert_called_once()
        assert result.success is True

    @pytest.mark.asyncio
    async def test_no_delete_when_no_existing_doc(
        self,
        processor: EmbeddingProcessorUseCase,
        mock_vector_store: MagicMock,
        mock_book_catalog: MagicMock,
    ) -> None:
        """Verifica que nao ha delete quando nao existe documento no MongoDB."""
        # find_by_stable_key retorna None (livro novo)
        mock_book_catalog.find_by_stable_key = AsyncMock(return_value=None)

        book = BookMetadata(gutenberg_id="42", title="Test Book")

        result = await processor.execute(
            book=book,
            artifact_key="gutenberg/42/v1.txt",
            checksum="abc123",
        )

        # Nao deve chamar delete pois nao ha documento existente
        mock_vector_store.delete_by_fingerprint.assert_not_called()
        # Insert deve ser chamado normalmente
        mock_vector_store.insert_embeddings.assert_called_once()
        assert result.success is True
