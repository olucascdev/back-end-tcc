"""
Testes do cliente Crossref.

Verifica normalizacao de campos, extracao de ano e paginacao.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import Settings
from app.infrastructure.sources.crossref_client import CrossrefClient


@pytest.fixture
def settings() -> Settings:
    """Configuracoes padrao para testes."""
    return Settings()


@pytest.fixture
def client(settings: Settings) -> CrossrefClient:
    """Cliente Crossref para testes."""
    return CrossrefClient(settings)


class TestCrossrefNormalize:
    """Testes de normalizacao de trabalhos Crossref."""

    def test_normalize_full_work(self, client: CrossrefClient) -> None:
        """Verifica normalizacao de trabalho completo."""
        work = {
            "DOI": "10.1234/test.2023.001",
            "title": ["Machine Learning in Healthcare"],
            "author": [
                {"given": "John", "family": "Doe"},
                {"given": "Jane", "family": "Smith"},
            ],
            "subject": ["Computer Science", "Healthcare"],
            "published-print": {"date-parts": [[2023, 5, 15]]},
            "language": "en",
            "URL": "https://example.com/paper",
            "link": [
                {
                    "URL": "https://example.com/paper.pdf",
                    "content-type": "application/pdf",
                }
            ],
            "abstract": "This paper explores ML applications in healthcare.",
        }

        result = client._normalize_work(work)

        assert result["source_id"] == "10.1234/test.2023.001"
        assert result["source_provider"] == "crossref"
        assert result["title"] == "Machine Learning in Healthcare"
        assert result["authors"] == ["John Doe", "Jane Smith"]
        assert result["subjects"] == ["Computer Science", "Healthcare"]
        assert result["year"] == 2023
        assert result["language"] == "en"
        assert result["doi"] == "10.1234/test.2023.001"
        assert result["url"] == "https://example.com/paper.pdf"
        assert result["abstract"] == "This paper explores ML applications in healthcare."
        assert result["source"] == "crossref"

    def test_normalize_minimal_work(self, client: CrossrefClient) -> None:
        """Verifica normalizacao de trabalho minimo."""
        work = {
            "DOI": "10.5555/minimal",
            "title": ["Simple Paper"],
        }

        result = client._normalize_work(work)

        assert result["source_id"] == "10.5555/minimal"
        assert result["source_provider"] == "crossref"
        assert result["title"] == "Simple Paper"
        assert result["authors"] == []
        assert result["subjects"] == []
        assert result["year"] is None
        assert result["url"] is None

    def test_normalize_year_from_published_online(self, client: CrossrefClient) -> None:
        """Verifica extracao de ano de published-online."""
        work = {
            "DOI": "10.1111/online",
            "title": ["Online First Paper"],
            "published-online": {"date-parts": [[2022, 3, 10]]},
        }

        result = client._normalize_work(work)

        assert result["year"] == 2022

    def test_normalize_year_from_created(self, client: CrossrefClient) -> None:
        """Verifica extracao de ano de created como fallback."""
        work = {
            "DOI": "10.2222/created",
            "title": ["Created Date Paper"],
            "created": {"date-parts": [[2021, 1, 1]]},
        }

        result = client._normalize_work(work)

        assert result["year"] == 2021

    def test_normalize_year_priority(self, client: CrossrefClient) -> None:
        """Verifica prioridade de extracao de ano."""
        work = {
            "DOI": "10.3333/priority",
            "title": ["Priority Paper"],
            "published-print": {"date-parts": [[2020, 1, 1]]},
            "published-online": {"date-parts": [[2019, 1, 1]]},
            "created": {"date-parts": [[2018, 1, 1]]},
        }

        result = client._normalize_work(work)

        # published-print tem prioridade
        assert result["year"] == 2020

    def test_normalize_url_fallback_to_general_url(self, client: CrossrefClient) -> None:
        """Verifica que URL geral e usado quando nao ha PDF link."""
        work = {
            "DOI": "10.4444/nopdf",
            "title": ["No PDF Paper"],
            "URL": "https://example.com/paper-page",
        }

        result = client._normalize_work(work)

        assert result["url"] == "https://example.com/paper-page"

    def test_normalize_string_subject(self, client: CrossrefClient) -> None:
        """Verifica que subject string e convertido para lista."""
        work = {
            "DOI": "10.5555/strsubject",
            "title": ["String Subject Paper"],
            "subject": "Single Subject",
        }

        result = client._normalize_work(work)

        assert result["subjects"] == ["Single Subject"]


class TestCrossrefSearch:
    """Testes de busca no Crossref."""

    @pytest.mark.asyncio
    async def test_search_returns_normalized_works(
        self, client: CrossrefClient
    ) -> None:
        """Verifica que busca retorna trabalhos normalizados."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "ok",
            "message": {
                "total-results": 2,
                "items": [
                    {
                        "DOI": "10.1000/one",
                        "title": ["Paper One"],
                        "author": [{"given": "Author", "family": "One"}],
                        "published-print": {"date-parts": [[2023, 1, 1]]},
                    },
                    {
                        "DOI": "10.1000/two",
                        "title": ["Paper Two"],
                    },
                ],
            },
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            results = await client.search_works(limit=2)

        assert len(results) == 2
        assert results[0]["title"] == "Paper One"
        assert results[0]["source_id"] == "10.1000/one"
        assert results[1]["title"] == "Paper Two"

    @pytest.mark.asyncio
    async def test_search_empty_response(self, client: CrossrefClient) -> None:
        """Verifica que resposta vazia retorna lista vazia."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "ok",
            "message": {"total-results": 0, "items": []},
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            results = await client.search_works()

        assert results == []

    @pytest.mark.asyncio
    async def test_search_filters_works_without_title(
        self, client: CrossrefClient
    ) -> None:
        """Verifica que trabalhos sem titulo sao filtrados."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "ok",
            "message": {
                "items": [
                    {"DOI": "10.1000/has-title", "title": ["Has Title"]},
                    {"DOI": "10.1000/no-title"},  # Sem titulo
                ],
            },
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            results = await client.search_works()

        assert len(results) == 1
        assert results[0]["title"] == "Has Title"
