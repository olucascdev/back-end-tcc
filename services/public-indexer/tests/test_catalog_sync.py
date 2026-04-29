"""
Testes do caso de uso CatalogSyncUseCase.

Verifica sincronizacao, deduplicacao e contagens.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.application.catalog_sync import CatalogSyncUseCase
from app.domain.services import BookCatalogService
from app.infrastructure.sources.gutenberg_client import GutenbergClient
from app.infrastructure.sources.open_library_client import OpenLibraryClient


@pytest.fixture
def mock_book_catalog() -> MagicMock:
    """Mock do servico de catalogo."""
    catalog = MagicMock(spec=BookCatalogService)
    catalog.upsert_book = AsyncMock(return_value={"upserted": True, "modified": False})
    return catalog


@pytest.fixture
def mock_open_library() -> MagicMock:
    """Mock do cliente Open Library."""
    client = MagicMock(spec=OpenLibraryClient)
    client.search_books = AsyncMock(
        return_value=[
            {
                "ol_key": "/works/OL1W",
                "title": "Book One",
                "authors": ["Author A"],
                "language": "eng",
                "subjects": ["Fiction"],
                "year": 2000,
                "formats": ["ebook"],
                "source": "openlibrary",
            },
            {
                "ol_key": "/works/OL2W",
                "title": "Book Two",
                "authors": ["Author B"],
                "language": "eng",
                "subjects": [],
                "year": 2001,
                "formats": [],
                "source": "openlibrary",
            },
        ]
    )
    return client


@pytest.fixture
def mock_gutenberg() -> MagicMock:
    """Mock do cliente Gutenberg."""
    client = MagicMock(spec=GutenbergClient)
    client.search_books = AsyncMock(
        return_value=[
            {"gutenberg_id": "100", "source": "gutenberg"},
            {"gutenberg_id": "101", "source": "gutenberg"},
        ]
    )
    client.fetch_book_page = AsyncMock(
        side_effect=[
            {
                "gutenberg_id": "100",
                "title": "Gutenberg Book 100",
                "authors": ["Gutenberg Author"],
                "language": "eng",
                "subjects": ["Classic"],
                "formats": ["txt", "epub"],
                "download_urls": {"txt": "https://example.com/100.txt"},
                "source": "gutenberg",
            },
            {
                "gutenberg_id": "101",
                "title": "Gutenberg Book 101",
                "authors": ["Another Author"],
                "language": "por",
                "subjects": [],
                "formats": ["txt"],
                "download_urls": {"txt": "https://example.com/101.txt"},
                "source": "gutenberg",
            },
        ]
    )
    return client


@pytest.fixture
def use_case(
    mock_book_catalog: MagicMock,
    mock_open_library: MagicMock,
    mock_gutenberg: MagicMock,
) -> CatalogSyncUseCase:
    """Caso de uso com mocks injetados."""
    return CatalogSyncUseCase(
        book_catalog=mock_book_catalog,
        open_library_client=mock_open_library,
        gutenberg_client=mock_gutenberg,
        batch_size=100,
    )


class TestCatalogSyncBothSources:
    """Testes de sincronizacao com ambas as fontes."""

    @pytest.mark.asyncio
    async def test_sync_both_sources(self, use_case: CatalogSyncUseCase) -> None:
        """Verifica sincronizacao de ambas as fontes."""
        reports = await use_case.execute()

        assert "openlibrary" in reports
        assert "gutenberg" in reports

        ol_report = reports["openlibrary"]
        assert ol_report.new == 2  # 2 livros do Open Library
        assert ol_report.errors == 0

        gutenberg_report = reports["gutenberg"]
        assert gutenberg_report.new == 2  # 2 livros do Gutenberg
        assert gutenberg_report.errors == 0

    @pytest.mark.asyncio
    async def test_sync_openlibrary_only(self, use_case: CatalogSyncUseCase) -> None:
        """Verifica sincronizacao apenas do Open Library."""
        reports = await use_case.execute(source_filter="openlibrary")

        assert "openlibrary" in reports
        assert "gutenberg" not in reports

    @pytest.mark.asyncio
    async def test_sync_gutenberg_only(self, use_case: CatalogSyncUseCase) -> None:
        """Verifica sincronizacao apenas do Gutenberg."""
        reports = await use_case.execute(source_filter="gutenberg")

        assert "gutenberg" in reports
        assert "openlibrary" not in reports


class TestCatalogSyncDedup:
    """Testes de deduplicacao."""

    @pytest.mark.asyncio
    async def test_sync_tracks_updated_books(
        self,
        mock_book_catalog: MagicMock,
        mock_open_library: MagicMock,
        mock_gutenberg: MagicMock,
    ) -> None:
        """Verifica que livros existentes sao marcados como updated."""
        mock_book_catalog.upsert_book = AsyncMock(
            return_value={"upserted": False, "modified": True}
        )

        use_case = CatalogSyncUseCase(
            book_catalog=mock_book_catalog,
            open_library_client=mock_open_library,
            gutenberg_client=mock_gutenberg,
            batch_size=100,
        )

        reports = await use_case.execute(source_filter="openlibrary")

        assert reports["openlibrary"].updated == 2
        assert reports["openlibrary"].new == 0

    @pytest.mark.asyncio
    async def test_sync_tracks_unchanged_books(
        self,
        mock_book_catalog: MagicMock,
        mock_open_library: MagicMock,
        mock_gutenberg: MagicMock,
    ) -> None:
        """Verifica que livros inalterados sao contados."""
        mock_book_catalog.upsert_book = AsyncMock(
            return_value={"upserted": False, "modified": False}
        )

        use_case = CatalogSyncUseCase(
            book_catalog=mock_book_catalog,
            open_library_client=mock_open_library,
            gutenberg_client=mock_gutenberg,
            batch_size=100,
        )

        reports = await use_case.execute(source_filter="openlibrary")

        assert reports["openlibrary"].unchanged == 2


class TestCatalogSyncErrors:
    """Testes de tratamento de erros."""

    @pytest.mark.asyncio
    async def test_sync_handles_individual_errors(
        self,
        mock_book_catalog: MagicMock,
        mock_open_library: MagicMock,
        mock_gutenberg: MagicMock,
    ) -> None:
        """Verifica que erros individuais nao falham o sync inteiro."""
        call_count = 0

        async def flaky_upsert(book):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Transient error")
            return {"upserted": True, "modified": False}

        mock_book_catalog.upsert_book = flaky_upsert

        use_case = CatalogSyncUseCase(
            book_catalog=mock_book_catalog,
            open_library_client=mock_open_library,
            gutenberg_client=mock_gutenberg,
            batch_size=100,
        )

        reports = await use_case.execute(source_filter="openlibrary")

        # 1 erro + 1 sucesso
        assert reports["openlibrary"].errors == 1
        assert reports["openlibrary"].new == 1

    @pytest.mark.asyncio
    async def test_sync_handles_source_failure(
        self,
        mock_book_catalog: MagicMock,
        mock_open_library: MagicMock,
        mock_gutenberg: MagicMock,
    ) -> None:
        """Verifica que falha total de fonte e reportada."""
        mock_open_library.search_books = AsyncMock(
            side_effect=RuntimeError("API unavailable")
        )

        use_case = CatalogSyncUseCase(
            book_catalog=mock_book_catalog,
            open_library_client=mock_open_library,
            gutenberg_client=mock_gutenberg,
            batch_size=100,
        )

        reports = await use_case.execute(source_filter="openlibrary")

        assert reports["openlibrary"].errors == 1
        assert len(reports["openlibrary"].details) > 0
