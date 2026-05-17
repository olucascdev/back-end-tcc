"""
Fabrica de clientes de fontes externas.

Fornece funcoes de factory para criar clientes de Open Library,
Project Gutenberg, OpenAlex, arXiv e Crossref com configuracao centralizada.
"""

from __future__ import annotations

from app.core.config import Settings
from app.infrastructure.sources.arxiv_client import ArxivClient
from app.infrastructure.sources.crossref_client import CrossrefClient
from app.infrastructure.sources.gutenberg_client import GutenbergClient
from app.infrastructure.sources.open_library_client import OpenLibraryClient
from app.infrastructure.sources.openalex_client import OpenAlexClient


def create_open_library_client(settings: Settings) -> OpenLibraryClient:
    """
    Cria cliente Open Library com configuracao do app.

    Args:
        settings: configuracoes do public-indexer.

    Returns:
        Instancia de OpenLibraryClient.
    """
    return OpenLibraryClient(settings)


def create_gutenberg_client(settings: Settings) -> GutenbergClient:
    """
    Cria cliente Project Gutenberg com configuracao do app.

    Args:
        settings: configuracoes do public-indexer.

    Returns:
        Instancia de GutenbergClient.
    """
    return GutenbergClient(settings)


def create_openalex_client(settings: Settings) -> OpenAlexClient:
    """
    Cria cliente OpenAlex com configuracao do app.

    Args:
        settings: configuracoes do public-indexer.

    Returns:
        Instancia de OpenAlexClient.
    """
    return OpenAlexClient(settings)


def create_arxiv_client(settings: Settings) -> ArxivClient:
    """
    Cria cliente arXiv com configuracao do app.

    Args:
        settings: configuracoes do public-indexer.

    Returns:
        Instancia de ArxivClient.
    """
    return ArxivClient(settings)


def create_crossref_client(settings: Settings) -> CrossrefClient:
    """
    Cria cliente Crossref com configuracao do app.

    Args:
        settings: configuracoes do public-indexer.

    Returns:
        Instancia de CrossrefClient.
    """
    return CrossrefClient(settings)
