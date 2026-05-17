"""
Testes do caso de uso CatalogSyncUseCase.

Verifica sincronizacao, deduplicacao e contagens.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.application.catalog_sync import CatalogSyncUseCase
from app.domain.services import BookCatalogService
from app.infrastructure.sources.arxiv_client import ArxivClient
from app.infrastructure.sources.crossref_client import CrossrefClient
from app.infrastructure.sources.gutenberg_client import GutenbergClient
from app.infrastructure.sources.open_library_client import OpenLibraryClient
from app.infrastructure.sources.openalex_client import OpenAlexClient


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


# Fixtures para novas fontes cientificas

@pytest.fixture
def mock_openalex() -> MagicMock:
    """Mock do cliente OpenAlex."""
    client = MagicMock(spec=OpenAlexClient)
    client.search_works = AsyncMock(
        return_value=(
            [
                {
                    "source_id": "W123456",
                    "source_provider": "openalex",
                    "title": "OpenAlex Paper One",
                    "authors": ["Author A"],
                    "language": "en",
                    "subjects": ["Machine Learning"],
                    "year": 2023,
                    "doi": "10.1234/test",
                    "url": "https://example.com/paper.pdf",
                    "source": "openalex",
                },
                {
                    "source_id": "W789012",
                    "source_provider": "openalex",
                    "title": "OpenAlex Paper Two",
                    "authors": ["Author B"],
                    "subjects": [],
                    "year": 2022,
                    "source": "openalex",
                },
            ],
            None,  # next_cursor
        )
    )
    return client


@pytest.fixture
def mock_arxiv() -> MagicMock:
    """Mock do cliente arXiv."""
    client = MagicMock(spec=ArxivClient)
    client.search_papers = AsyncMock(
        return_value=[
            {
                "source_id": "2101.12345",
                "source_provider": "arxiv",
                "title": "arXiv Paper One",
                "authors": ["Author C"],
                "language": None,
                "subjects": ["cs.LG"],
                "year": 2021,
                "url": "https://arxiv.org/pdf/2101.12345.pdf",
                "abstract": "Abstract text",
                "source": "arxiv",
            },
        ]
    )
    return client


@pytest.fixture
def mock_crossref() -> MagicMock:
    """Mock do cliente Crossref."""
    client = MagicMock(spec=CrossrefClient)
    client.search_works = AsyncMock(
        return_value=[
            {
                "source_id": "10.1000/crossref1",
                "source_provider": "crossref",
                "title": "Crossref Paper One",
                "authors": ["Author D"],
                "language": "en",
                "subjects": ["Computer Science"],
                "year": 2023,
                "doi": "10.1000/crossref1",
                "url": "https://example.com/crossref.pdf",
                "source": "crossref",
            },
        ]
    )
    return client


class TestCatalogSyncOpenAlex:
    """Testes de sincronizacao com OpenAlex."""

    @pytest.fixture
    def use_case_with_openalex(
        self,
        mock_book_catalog: MagicMock,
        mock_open_library: MagicMock,
        mock_gutenberg: MagicMock,
        mock_openalex: MagicMock,
    ) -> CatalogSyncUseCase:
        """Caso de uso com OpenAlex injetado."""
        return CatalogSyncUseCase(
            book_catalog=mock_book_catalog,
            open_library_client=mock_open_library,
            gutenberg_client=mock_gutenberg,
            openalex_client=mock_openalex,
            batch_size=100,
        )

    @pytest.mark.asyncio
    async def test_sync_openalex(
        self, use_case_with_openalex: CatalogSyncUseCase
    ) -> None:
        """Verifica sincronizacao do OpenAlex."""
        reports = await use_case_with_openalex.execute(source_filter="openalex")

        assert "openalex" in reports
        assert reports["openalex"].new == 2
        assert reports["openalex"].errors == 0

    @pytest.mark.asyncio
    async def test_sync_openalex_missing_client(
        self,
        mock_book_catalog: MagicMock,
        mock_open_library: MagicMock,
        mock_gutenberg: MagicMock,
    ) -> None:
        """Verifica que fonte sem cliente retorna erro."""
        use_case = CatalogSyncUseCase(
            book_catalog=mock_book_catalog,
            open_library_client=mock_open_library,
            gutenberg_client=mock_gutenberg,
            batch_size=100,
        )

        reports = await use_case.execute(source_filter="openalex")

        assert "openalex" in reports
        assert reports["openalex"].errors == 1


class TestCatalogSyncArxiv:
    """Testes de sincronizacao com arXiv."""

    @pytest.fixture
    def use_case_with_arxiv(
        self,
        mock_book_catalog: MagicMock,
        mock_open_library: MagicMock,
        mock_gutenberg: MagicMock,
        mock_arxiv: MagicMock,
    ) -> CatalogSyncUseCase:
        """Caso de uso com arXiv injetado."""
        return CatalogSyncUseCase(
            book_catalog=mock_book_catalog,
            open_library_client=mock_open_library,
            gutenberg_client=mock_gutenberg,
            arxiv_client=mock_arxiv,
            batch_size=100,
        )

    @pytest.mark.asyncio
    async def test_sync_arxiv(
        self, use_case_with_arxiv: CatalogSyncUseCase
    ) -> None:
        """Verifica sincronizacao do arXiv."""
        reports = await use_case_with_arxiv.execute(source_filter="arxiv")

        assert "arxiv" in reports
        assert reports["arxiv"].new == 1
        assert reports["arxiv"].errors == 0

    @pytest.mark.asyncio
    async def test_sync_arxiv_missing_client(
        self,
        mock_book_catalog: MagicMock,
        mock_open_library: MagicMock,
        mock_gutenberg: MagicMock,
    ) -> None:
        """Verifica que fonte sem cliente retorna erro."""
        use_case = CatalogSyncUseCase(
            book_catalog=mock_book_catalog,
            open_library_client=mock_open_library,
            gutenberg_client=mock_gutenberg,
            batch_size=100,
        )

        reports = await use_case.execute(source_filter="arxiv")

        assert "arxiv" in reports
        assert reports["arxiv"].errors == 1


class TestCatalogSyncCrossref:
    """Testes de sincronizacao com Crossref."""

    @pytest.fixture
    def use_case_with_crossref(
        self,
        mock_book_catalog: MagicMock,
        mock_open_library: MagicMock,
        mock_gutenberg: MagicMock,
        mock_crossref: MagicMock,
    ) -> CatalogSyncUseCase:
        """Caso de uso com Crossref injetado."""
        return CatalogSyncUseCase(
            book_catalog=mock_book_catalog,
            open_library_client=mock_open_library,
            gutenberg_client=mock_gutenberg,
            crossref_client=mock_crossref,
            batch_size=100,
        )

    @pytest.mark.asyncio
    async def test_sync_crossref(
        self, use_case_with_crossref: CatalogSyncUseCase
    ) -> None:
        """Verifica sincronizacao do Crossref."""
        reports = await use_case_with_crossref.execute(source_filter="crossref")

        assert "crossref" in reports
        assert reports["crossref"].new == 1
        assert reports["crossref"].errors == 0

    @pytest.mark.asyncio
    async def test_sync_crossref_missing_client(
        self,
        mock_book_catalog: MagicMock,
        mock_open_library: MagicMock,
        mock_gutenberg: MagicMock,
    ) -> None:
        """Verifica que fonte sem cliente retorna erro."""
        use_case = CatalogSyncUseCase(
            book_catalog=mock_book_catalog,
            open_library_client=mock_open_library,
            gutenberg_client=mock_gutenberg,
            batch_size=100,
        )

        reports = await use_case.execute(source_filter="crossref")

        assert "crossref" in reports
        assert reports["crossref"].errors == 1


class TestCatalogSyncAllSources:
    """Testes de sincronizacao com todas as fontes juntas."""

    @pytest.fixture
    def use_case_all_sources(
        self,
        mock_book_catalog: MagicMock,
        mock_open_library: MagicMock,
        mock_gutenberg: MagicMock,
        mock_openalex: MagicMock,
        mock_arxiv: MagicMock,
        mock_crossref: MagicMock,
    ) -> CatalogSyncUseCase:
        """Caso de uso com todas as fontes injetadas."""
        return CatalogSyncUseCase(
            book_catalog=mock_book_catalog,
            open_library_client=mock_open_library,
            gutenberg_client=mock_gutenberg,
            openalex_client=mock_openalex,
            arxiv_client=mock_arxiv,
            crossref_client=mock_crossref,
            batch_size=100,
        )

    @pytest.mark.asyncio
    async def test_sync_all_sources(
        self, use_case_all_sources: CatalogSyncUseCase
    ) -> None:
        """Verifica sincronizacao de todas as fontes."""
        reports = await use_case_all_sources.execute()

        assert "openlibrary" in reports
        assert "gutenberg" in reports
        assert "openalex" in reports
        assert "arxiv" in reports
        assert "crossref" in reports
