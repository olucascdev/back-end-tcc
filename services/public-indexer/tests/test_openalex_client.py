"""
Testes do cliente OpenAlex.

Verifica normalizacao de campos, paginacao por cursor e retry.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import Settings
from app.infrastructure.sources.openalex_client import OpenAlexClient, _reconstruct_abstract


@pytest.fixture
def settings() -> Settings:
    """Configuracoes padrao para testes."""
    return Settings()


@pytest.fixture
def client(settings: Settings) -> OpenAlexClient:
    """Cliente OpenAlex para testes."""
    return OpenAlexClient(settings)


class TestOpenAlexNormalize:
    """Testes de normalizacao de trabalhos OpenAlex."""

    def test_normalize_full_work(self, client: OpenAlexClient) -> None:
        """Verifica normalizacao de trabalho completo."""
        work = {
            "id": "https://openalex.org/W1234567890",
            "title": "Deep Learning for Natural Language Processing",
            "authorships": [
                {"author": {"display_name": "John Doe"}},
                {"author": {"display_name": "Jane Smith"}},
            ],
            "concepts": [
                {"display_name": "Machine Learning"},
                {"display_name": "Natural Language Processing"},
            ],
            "publication_year": 2023,
            "language": "en",
            "open_access": {
                "oa_url": "https://example.com/paper.pdf",
            },
            "doi": "https://doi.org/10.1234/test.2023.001",
        }

        result = client._normalize_work(work)

        assert result["source_id"] == "W1234567890"
        assert result["source_provider"] == "openalex"
        assert result["title"] == "Deep Learning for Natural Language Processing"
        assert result["authors"] == ["John Doe", "Jane Smith"]
        assert result["subjects"] == ["Machine Learning", "Natural Language Processing"]
        assert result["year"] == 2023
        assert result["language"] == "en"
        assert result["url"] == "https://example.com/paper.pdf"
        assert result["doi"] == "10.1234/test.2023.001"
        assert result["source"] == "openalex"

    def test_normalize_minimal_work(self, client: OpenAlexClient) -> None:
        """Verifica normalizacao de trabalho minimo."""
        work = {
            "id": "https://openalex.org/W999",
            "title": "Simple Paper",
        }

        result = client._normalize_work(work)

        assert result["source_id"] == "W999"
        assert result["source_provider"] == "openalex"
        assert result["title"] == "Simple Paper"
        assert result["authors"] == []
        assert result["subjects"] == []
        assert result["year"] is None
        assert result["url"] is None
        assert result["doi"] is None

    def test_normalize_doi_strips_prefix(self, client: OpenAlexClient) -> None:
        """Verifica que prefixo https://doi.org/ e removido do DOI."""
        work = {
            "id": "https://openalex.org/W1",
            "title": "Paper with DOI",
            "doi": "https://doi.org/10.5555/example",
        }

        result = client._normalize_work(work)

        assert result["doi"] == "10.5555/example"

    def test_normalize_no_open_access(self, client: OpenAlexClient) -> None:
        """Verifica que URL e None quando nao ha open_access."""
        work = {
            "id": "https://openalex.org/W2",
            "title": "Closed Paper",
            "open_access": {},
        }

        result = client._normalize_work(work)

        assert result["url"] is None


class TestOpenAlexSearch:
    """Testes de busca no OpenAlex."""

    @pytest.mark.asyncio
    async def test_search_returns_normalized_works(
        self, client: OpenAlexClient
    ) -> None:
        """Verifica que busca retorna trabalhos normalizados."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "meta": {"next_cursor": "cursor123"},
            "results": [
                {
                    "id": "https://openalex.org/W1",
                    "title": "Paper One",
                    "authorships": [{"author": {"display_name": "Author A"}}],
                    "publication_year": 2020,
                },
                {
                    "id": "https://openalex.org/W2",
                    "title": "Paper Two",
                    "authorships": [],
                },
            ],
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            results, next_cursor = await client.search_works(limit=2)

        assert len(results) == 2
        assert results[0]["title"] == "Paper One"
        assert results[0]["source_id"] == "W1"
        assert next_cursor == "cursor123"

    @pytest.mark.asyncio
    async def test_search_empty_response(self, client: OpenAlexClient) -> None:
        """Verifica que resposta vazia retorna lista vazia."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"meta": {}, "results": []}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            results, next_cursor = await client.search_works()

        assert results == []
        assert next_cursor is None

    @pytest.mark.asyncio
    async def test_search_filters_works_without_title(
        self, client: OpenAlexClient
    ) -> None:
        """Verifica que trabalhos sem titulo sao filtrados."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "meta": {},
            "results": [
                {"id": "https://openalex.org/W1", "title": "Has Title"},
                {"id": "https://openalex.org/W2"},  # Sem titulo
            ],
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            results, _ = await client.search_works()

        assert len(results) == 1
        assert results[0]["title"] == "Has Title"


class TestReconstructAbstract:
    """Testes da funcao de reconstrucao de abstract do OpenAlex."""

    def test_reconstruct_full_abstract(self) -> None:
        """Verifica reconstrucao de abstract com inverted index completo."""
        inverted_index = {
            "This": [0],
            "is": [1],
            "a": [2],
            "sample": [3],
            "abstract": [4],
        }

        result = _reconstruct_abstract(inverted_index)

        assert result == "This is a sample abstract"

    def test_reconstruct_complex_abstract(self) -> None:
        """Verifica reconstrucao com palavras repetidas em posicoes diferentes."""
        inverted_index = {
            "The": [0, 6],
            "study": [1],
            "of": [2],
            "machine": [3],
            "learning": [4],
            "is": [5],
            "important": [7],
        }

        result = _reconstruct_abstract(inverted_index)

        assert result == "The study of machine learning is The important"

    def test_reconstruct_none_returns_none(self) -> None:
        """Verifica que None retorna None."""
        assert _reconstruct_abstract(None) is None

    def test_reconstruct_empty_dict_returns_none(self) -> None:
        """Verifica que dict vazio retorna None."""
        assert _reconstruct_abstract({}) is None

    def test_reconstruct_non_dict_returns_none(self) -> None:
        """Verifica que valor nao-dict retorna None."""
        assert _reconstruct_abstract("not a dict") is None  # type: ignore[arg-type]

    def test_normalize_work_with_abstract_inverted_index(
        self, client: OpenAlexClient
    ) -> None:
        """Verifica que _normalize_work converte inverted index para string."""
        work = {
            "id": "https://openalex.org/W1",
            "title": "Paper with Abstract",
            "abstract_inverted_index": {
                "This": [0],
                "paper": [1],
                "has": [2],
                "an": [3],
                "abstract": [4],
            },
        }

        result = client._normalize_work(work)

        assert result["abstract"] == "This paper has an abstract"
        assert isinstance(result["abstract"], str)

    def test_normalize_work_without_abstract(self, client: OpenAlexClient) -> None:
        """Verifica que trabalho sem abstract retorna None."""
        work = {
            "id": "https://openalex.org/W2",
            "title": "Paper without Abstract",
        }

        result = client._normalize_work(work)

        assert result["abstract"] is None
