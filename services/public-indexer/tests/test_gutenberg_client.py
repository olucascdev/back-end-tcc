"""
Testes do cliente Project Gutenberg.

Verifica parse de HTML, extracao de metadados e URLs de download.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import Settings
from app.infrastructure.sources.gutenberg_client import GutenbergClient


@pytest.fixture
def settings() -> Settings:
    """Configuracoes padrao para testes."""
    return Settings()


@pytest.fixture
def client(settings: Settings) -> GutenbergClient:
    """Cliente Gutenberg para testes."""
    return GutenbergClient(settings)


class TestGutenbergParseBookPage:
    """Testes de parse de pagina de livro Gutenberg."""

    def test_parse_full_page(self, client: GutenbergClient) -> None:
        """Verifica parse de pagina completa."""
        html = """
        <html>
        <body>
            <h1>The Great Gatsby</h1>
            <a href="/author/123">F. Scott Fitzgerald</a>
            <a href="/author/456">Editor Name</a>
            Language: English
            Subject: Fiction
            Subject: American literature
            <a href="/ebooks/12345.epub">epub</a>
            <a href="/ebooks/12345.txt">txt</a>
            <a href="/ebooks/12345.pdf">pdf</a>
        </body>
        </html>
        """

        result = client._parse_book_page(html, "12345")

        assert result["gutenberg_id"] == "12345"
        assert result["title"] == "The Great Gatsby"
        assert result["authors"] == ["F. Scott Fitzgerald", "Editor Name"]
        assert result["language"] == "English"
        assert result["subjects"] == ["Fiction", "American literature"]
        assert "epub" in result["formats"]
        assert "txt" in result["formats"]
        assert "pdf" in result["formats"]
        assert result["source"] == "gutenberg"

    def test_parse_minimal_page(self, client: GutenbergClient) -> None:
        """Verifica parse de pagina minima."""
        html = "<html><body><h1>Simple Book</h1></body></html>"

        result = client._parse_book_page(html, "99999")

        assert result["gutenberg_id"] == "99999"
        assert result["title"] == "Simple Book"
        assert result["authors"] == []
        assert result["language"] is None
        assert result["subjects"] == []
        assert result["formats"] == []

    def test_parse_download_urls(self, client: GutenbergClient) -> None:
        """Verifica extracao de URLs de download."""
        html = """
        <a href="/ebooks/123.epub.images">epub</a>
        <a href="/ebooks/123.txt.utf-8">txt</a>
        <a href="/ebooks/123.pdf">pdf</a>
        """

        urls = client._extract_download_urls(html)

        assert "epub" in urls
        assert "txt" in urls
        assert "pdf" in urls
        assert "gutenberg.org" in urls["txt"]


class TestGutenbergParseSearchResults:
    """Testes de parse de resultados de busca."""

    def test_parse_search_extracts_ids(self, client: GutenbergClient) -> None:
        """Verifica extracao de IDs da pagina de busca."""
        html = """
        <ul>
            <li><a href="/ebooks/1001">Book One</a></li>
            <li><a href="/ebooks/1002">Book Two</a></li>
            <li><a href="/ebooks/1003">Book Three</a></li>
        </ul>
        """

        results = client._parse_search_results(html, limit=10)

        assert len(results) == 3
        assert results[0]["gutenberg_id"] == "1001"
        assert results[1]["gutenberg_id"] == "1002"
        assert results[2]["gutenberg_id"] == "1003"

    def test_parse_search_respects_limit(self, client: GutenbergClient) -> None:
        """Verifica que limite e respeitado."""
        html = """
        <li><a href="/ebooks/1">A</a></li>
        <li><a href="/ebooks/2">B</a></li>
        <li><a href="/ebooks/3">C</a></li>
        <li><a href="/ebooks/4">D</a></li>
        """

        results = client._parse_search_results(html, limit=2)

        assert len(results) == 2

    def test_parse_search_deduplicates(self, client: GutenbergClient) -> None:
        """Verifica que IDs duplicados sao removidos."""
        html = """
        <li><a href="/ebooks/1">A</a></li>
        <li><a href="/ebooks/1">A</a></li>
        <li><a href="/ebooks/2">B</a></li>
        """

        results = client._parse_search_results(html, limit=10)

        assert len(results) == 2


class TestGutenbergFetchBookPage:
    """Testes de busca de pagina de livro."""

    @pytest.mark.asyncio
    async def test_fetch_book_page_returns_parsed_data(
        self, client: GutenbergClient
    ) -> None:
        """Verifica que fetch_book_page retorna dados parseados."""
        html = """
        <html><body>
            <h1>Test Book</h1>
            <a href="/author/1">Author</a>
            Language: English
            <a href="/ebooks/42.txt">txt</a>
        </body></html>
        """

        with patch.object(client, "_request_with_retry", return_value=html):
            result = await client.fetch_book_page("42")

        assert result is not None
        assert result["gutenberg_id"] == "42"
        assert result["title"] == "Test Book"

    @pytest.mark.asyncio
    async def test_fetch_book_page_returns_none_on_failure(
        self, client: GutenbergClient
    ) -> None:
        """Verifica que retorna None em caso de falha."""
        with patch.object(client, "_request_with_retry", return_value=None):
            result = await client.fetch_book_page("999")

        assert result is None
