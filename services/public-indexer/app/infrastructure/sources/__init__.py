"""
Fabrica de clientes de fontes externas.

Fornece funcoes de factory para criar clientes de Open Library
e Project Gutenberg com configuracao centralizada.
"""

from __future__ import annotations

from app.core.config import Settings
from app.infrastructure.sources.gutenberg_client import GutenbergClient
from app.infrastructure.sources.open_library_client import OpenLibraryClient


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
