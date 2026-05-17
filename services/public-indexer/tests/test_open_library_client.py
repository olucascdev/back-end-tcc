"""
Testes do cliente Open Library.

Verifica normalizacao de campos, paginacao e retry.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import Settings
from app.infrastructure.sources.open_library_client import OpenLibraryClient


@pytest.fixture
def settings() -> Settings:
    """Configuracoes padrao para testes."""
    return Settings()


@pytest.fixture
def client(settings: Settings) -> OpenLibraryClient:
    """Cliente Open Library para testes."""
    return OpenLibraryClient(settings)


class TestOpenLibraryNormalize:
    """Testes de normalizacao de documentos Open Library."""

    def test_normalize_full_doc(self, client: OpenLibraryClient) -> None:
        """Verifica normalizacao de documento completo."""
        doc = {
            "key": "/works/OL123W",
            "title": "Dom Casmurro",
            "author_name": ["Machado de Assis"],
            "language": ["por"],
            "subject": ["Brazilian literature", "Fiction"],
            "first_publish_year": 1899,
            "format": ["ebook"],
        }

        result = client._normalize_doc(doc)

        assert result["ol_key"] == "/works/OL123W"
        assert result["title"] == "Dom Casmurro"
        assert result["authors"] == ["Machado de Assis"]
        assert result["language"] == "por"
        assert result["subjects"] == ["Brazilian literature", "Fiction"]
        assert result["year"] == 1899
        assert result["formats"] == ["ebook"]
        assert result["source"] == "openlibrary"

    def test_normalize_minimal_doc(self, client: OpenLibraryClient) -> None:
        """Verifica normalizacao de documento minimo."""
        doc = {
            "key": "/works/OL456W",
            "title": "Unknown Book",
        }

        result = client._normalize_doc(doc)

        assert result["ol_key"] == "/works/OL456W"
        assert result["title"] == "Unknown Book"
        assert result["authors"] == []
        assert result["language"] is None
        assert result["subjects"] == []
        assert result["year"] is None

    def test_normalize_non_work_key(self, client: OpenLibraryClient) -> None:
        """Verifica que chaves nao-work resultam em ol_key None."""
        doc = {
            "key": "/authors/OL123A",
            "title": "Some Book",
        }

        result = client._normalize_doc(doc)

        assert result["ol_key"] is None

    def test_normalize_string_fields(self, client: OpenLibraryClient) -> None:
        """Verifica que campos string sao convertidos para lista."""
        doc = {
            "key": "/works/OL789W",
            "title": "Test Book",
            "author_name": "Single Author",
            "subject": "Single Subject",
            "format": "ebook",
        }

        result = client._normalize_doc(doc)

        assert result["authors"] == ["Single Author"]
        assert result["subjects"] == ["Single Subject"]
        assert result["formats"] == ["ebook"]


class TestOpenLibrarySearch:
    """Testes de busca no Open Library."""

    @pytest.mark.asyncio
    async def test_search_returns_normalized_books(
        self, client: OpenLibraryClient
    ) -> None:
        """Verifica que busca retorna livros normalizados."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "numFound": 2,
            "docs": [
                {
                    "key": "/works/OL1W",
                    "title": "Book One",
                    "author_name": ["Author A"],
                    "language": ["eng"],
                    "first_publish_year": 2000,
                },
                {
                    "key": "/works/OL2W",
                    "title": "Book Two",
                    "author_name": ["Author B"],
                },
            ],
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            results = await client.search_books(limit=2)

        assert len(results) == 2
        assert results[0]["title"] == "Book One"
        assert results[0]["ol_key"] == "/works/OL1W"
        assert results[1]["title"] == "Book Two"

    @pytest.mark.asyncio
    async def test_search_empty_response(self, client: OpenLibraryClient) -> None:
        """Verifica que resposta vazia retorna lista vazia."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"numFound": 0, "docs": []}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            results = await client.search_books()

        assert results == []

    @pytest.mark.asyncio
    async def test_search_filters_docs_without_title(
        self, client: OpenLibraryClient
    ) -> None:
        """Verifica que documentos sem titulo sao filtrados."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "docs": [
                {"key": "/works/OL1W", "title": "Has Title"},
                {"key": "/works/OL2W"},  # Sem titulo
            ],
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            results = await client.search_books()

        assert len(results) == 1
        assert results[0]["title"] == "Has Title"
