"""
Testes do cliente arXiv.

Verifica parse de feed Atom/XML, extracao de metadados e paginacao.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import Settings
from app.infrastructure.sources.arxiv_client import ArxivClient


# Feed Atom de exemplo do arXiv para testes
SAMPLE_ARXIV_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2101.12345v1</id>
    <title>Deep Learning Advances in 2021</title>
    <summary>This paper presents a comprehensive survey of deep learning advances.</summary>
    <published>2021-03-15T10:00:00Z</published>
    <author>
      <name>John Doe</name>
    </author>
    <author>
      <name>Jane Smith</name>
    </author>
    <category term="cs.LG" scheme="http://arxiv.org/schemas/atom"/>
    <category term="cs.AI" scheme="http://arxiv.org/schemas/atom"/>
    <link href="http://arxiv.org/abs/2101.12345v1" rel="alternate" type="text/html"/>
    <link href="http://arxiv.org/pdf/2101.12345v1" rel="related" type="application/pdf"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2102.67890v2</id>
    <title>Transformer Architectures Review</title>
    <summary>A review of transformer architectures for NLP tasks.</summary>
    <published>2021-04-20T14:30:00Z</published>
    <author>
      <name>Bob Johnson</name>
    </author>
    <category term="cs.CL" scheme="http://arxiv.org/schemas/atom"/>
    <link href="http://arxiv.org/abs/2102.67890v2" rel="alternate" type="text/html"/>
  </entry>
</feed>
"""


@pytest.fixture
def settings() -> Settings:
    """Configuracoes padrao para testes."""
    return Settings()


@pytest.fixture
def client(settings: Settings) -> ArxivClient:
    """Cliente arXiv para testes."""
    return ArxivClient(settings)


class TestArxivParseFeed:
    """Testes de parse do feed Atom/XML do arXiv."""

    def test_parse_full_feed(self, client: ArxivClient) -> None:
        """Verifica parse de feed completo com multiplas entradas."""
        results = client._parse_feed(SAMPLE_ARXIV_FEED)

        assert len(results) == 2

        # Primeira entrada
        first = results[0]
        assert first["source_id"] == "2101.12345"
        assert first["source_provider"] == "arxiv"
        assert first["title"] == "Deep Learning Advances in 2021"
        assert first["authors"] == ["John Doe", "Jane Smith"]
        assert first["year"] == 2021
        assert first["abstract"] == "This paper presents a comprehensive survey of deep learning advances."
        assert first["subjects"] == ["cs.LG", "cs.AI"]
        assert first["url"] == "http://arxiv.org/pdf/2101.12345v1"
        assert first["source"] == "arxiv"

        # Segunda entrada
        second = results[1]
        assert second["source_id"] == "2102.67890"
        assert second["title"] == "Transformer Architectures Review"
        assert second["authors"] == ["Bob Johnson"]
        assert second["year"] == 2021

    def test_parse_empty_feed(self, client: ArxivClient) -> None:
        """Verifica parse de feed vazio."""
        empty_feed = '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>'
        results = client._parse_feed(empty_feed)

        assert results == []

    def test_parse_invalid_xml(self, client: ArxivClient) -> None:
        """Verifica que XML invalido retorna lista vazia."""
        results = client._parse_feed("not valid xml at all")

        assert results == []

    def test_parse_entry_without_title(self, client: ArxivClient) -> None:
        """Verifica que entradas sem titulo sao ignoradas."""
        feed = """<?xml version="1.0"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry>
            <id>http://arxiv.org/abs/2101.00000</id>
            <summary>No title entry</summary>
          </entry>
        </feed>
        """
        results = client._parse_feed(feed)

        assert results == []

    def test_parse_pdf_url_fallback(self, client: ArxivClient) -> None:
        """Verifica que URL do PDF e construida quando nao ha link explicito."""
        feed = """<?xml version="1.0"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry>
            <id>http://arxiv.org/abs/2101.99999v1</id>
            <title>Paper Without PDF Link</title>
            <published>2021-01-01T00:00:00Z</published>
          </entry>
        </feed>
        """
        results = client._parse_feed(feed)

        assert len(results) == 1
        assert results[0]["url"] == "https://arxiv.org/pdf/2101.99999.pdf"


class TestArxivSearch:
    """Testes de busca no arXiv."""

    @pytest.mark.asyncio
    async def test_search_returns_parsed_papers(
        self, client: ArxivClient
    ) -> None:
        """Verifica que busca retorna artigos parseados."""
        with patch.object(client, "_request_with_retry", return_value=SAMPLE_ARXIV_FEED):
            results = await client.search_papers(limit=2)

        assert len(results) == 2
        assert results[0]["title"] == "Deep Learning Advances in 2021"
        assert results[1]["title"] == "Transformer Architectures Review"

    @pytest.mark.asyncio
    async def test_search_empty_response(self, client: ArxivClient) -> None:
        """Verifica que resposta vazia retorna lista vazia."""
        with patch.object(client, "_request_with_retry", return_value=None):
            results = await client.search_papers()

        assert results == []
