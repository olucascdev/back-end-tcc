"""
Cliente assincrono para a API Google Books.

Serve como fonte alternativa (fallback) para busca de livros e publicacoes
quando outras fontes nao retornam resultados satisfatorios. Nao requer chave
de API para buscas basicas, mas suporta configuracao opcional.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

GOOGLE_BOOKS_BASE_URL = "https://www.googleapis.com/books/v1/volumes"


def _extract_book(item: dict[str, Any]) -> dict[str, Any]:
    """Extrai os campos relevantes de um item da API Google Books.

    Args:
        item: Dicionario bruto retornado pela API Google Books.

    Returns:
        Dicionario com campos padronizados: id, title, authors,
        description, info_link, preview_link.
    """
    volume_info = item.get("volumeInfo", {})

    return {
        "id": item.get("id", ""),
        "title": volume_info.get("title", ""),
        "authors": volume_info.get("authors", []),
        "description": volume_info.get("description", ""),
        "info_link": volume_info.get("infoLink"),
        "preview_link": volume_info.get("previewLink"),
    }


async def search_books(
    query: str,
    limit: int = 3,
    api_key: str | None = None,
) -> list[dict[str, Any]]:
    """Busca livros na API Google Books.

    Realiza uma busca por texto livre e retorna os resultados com metadados
    extraidos e padronizados. Esta funcao serve como fallback quando fontes
    primarias (OpenAlex, etc.) nao retornam resultados.

    Args:
        query: Termo de busca (titulo, autor, ISBN, etc.).
        limit: Numero maximo de resultados a retornar (padrao: 3).
        api_key: Chave de API opcional do Google Books. Se informada,
            aumenta os limites de requisicao da API.

    Returns:
        Lista de dicionarios com os metadados dos livros encontrados.
        Retorna lista vazia em caso de erro na API.
    """
    params: dict[str, str | int] = {
        "q": query,
        "maxResults": limit,
    }
    if api_key:
        params["key"] = api_key

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(GOOGLE_BOOKS_BASE_URL, params=params)
            response.raise_for_status()
            data = response.json()

        items = data.get("items", [])
        return [_extract_book(item) for item in items]

    except httpx.HTTPStatusError as exc:
        logger.warning(
            "Google Books API retornou erro HTTP %s para query '%s': %s",
            exc.response.status_code,
            query,
            exc.response.text[:200],
        )
        return []

    except httpx.RequestError as exc:
        logger.warning(
            "Falha na requisicao ao Google Books para query '%s': %s",
            query,
            exc,
        )
        return []

    except Exception as exc:
        logger.warning(
            "Erro inesperado ao buscar no Google Books para query '%s': %s",
            query,
            exc,
        )
        return []
