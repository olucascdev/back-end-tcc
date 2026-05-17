"""
Cliente assincrono para a API OpenAlex.

Permite buscar trabalhos academicos por consulta textual, extraindo
metadados relevantes como titulo, autores, resumo, acesso aberto e DOI.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

OPENALEX_BASE_URL = "https://api.openalex.org/works"


def _invert_abstract(inverted_index: dict[str, list[int]]) -> str:
    """Reconstroi o abstract a partir do formato invertido do OpenAlex.

    O OpenAlex armazena o abstract como um dicionario onde cada chave e uma
    palavra e o valor e uma lista de posicoes (indices) onde essa palavra
    aparece no texto original. Esta funcao inverte esse mapeamento de volta
    para uma string legivel.

    Args:
        inverted_index: Dicionario no formato {"palavra": [posicoes]}.

    Returns:
        O abstract reconstruido como string.
    """
    # Cria uma lista com tamanho suficiente para todas as posicoes
    max_pos = max(idx for positions in inverted_index.values() for idx in positions)
    tokens: list[str | None] = [None] * (max_pos + 1)

    for word, positions in inverted_index.items():
        for pos in positions:
            tokens[pos] = word

    return " ".join(token for token in tokens if token is not None)


def _extract_work(work: dict[str, Any]) -> dict[str, Any]:
    """Extrai os campos relevantes de um trabalho do OpenAlex.

    Args:
        work: Dicionario bruto retornado pela API OpenAlex.

    Returns:
        Dicionario com campos padronizados: id, title, authors, abstract,
        oa_url, doi, publication_year.
    """
    # Extrai lista de nomes de autores
    authorships = work.get("authorships", [])
    authors = [
        authorship.get("author", {}).get("display_name", "")
        for authorship in authorships
        if authorship.get("author", {}).get("display_name")
    ]

    # Inverte o abstract se estiver no formato invertido
    abstract = ""
    inverted_abstract = work.get("abstract_inverted_index")
    if inverted_abstract:
        abstract = _invert_abstract(inverted_abstract)

    # Extrai URL de acesso aberto
    open_access = work.get("open_access", {})
    oa_url = open_access.get("oa_url") if open_access else None

    return {
        "id": work.get("id", ""),
        "title": work.get("display_name", ""),
        "authors": authors,
        "abstract": abstract,
        "oa_url": oa_url,
        "doi": work.get("doi"),
        "publication_year": work.get("publication_year"),
    }


async def search_works(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Busca trabalhos academicos na API OpenAlex.

    Realiza uma busca por texto livre e retorna os resultados mais relevantes
    com metadados extraidos e padronizados.

    Args:
        query: Termo de busca (titulo, autor, palavras-chave, etc.).
        limit: Numero maximo de resultados a retornar (padrao: 5).

    Returns:
        Lista de dicionarios com os metadados dos trabalhos encontrados.
        Retorna lista vazia em caso de erro na API.
    """
    params = {
        "search": query,
        "per-page": limit,
        "sort": "relevance_score:desc",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(OPENALEX_BASE_URL, params=params)
            response.raise_for_status()
            data = response.json()

        results = data.get("results", [])
        return [_extract_work(work) for work in results]

    except httpx.HTTPStatusError as exc:
        logger.warning(
            "OpenAlex API retornou erro HTTP %s para query '%s': %s",
            exc.response.status_code,
            query,
            exc.response.text[:200],
        )
        return []

    except httpx.RequestError as exc:
        logger.warning(
            "Falha na requisicao ao OpenAlex para query '%s': %s",
            query,
            exc,
        )
        return []

    except Exception as exc:
        logger.warning(
            "Erro inesperado ao buscar no OpenAlex para query '%s': %s",
            query,
            exc,
        )
        return []
