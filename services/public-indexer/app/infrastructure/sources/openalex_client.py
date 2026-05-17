"""
Cliente assincrono para a API OpenAlex.

Responsavel por buscar metadados de trabalhos academicos via API REST JSON,
normalizar campos e lidar com paginacao e retries.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import Settings

logger = logging.getLogger(__name__)


def _reconstruct_abstract(inverted_index: dict[str, list[int]] | None) -> str | None:
    """
    Reconstrói o abstract em formato de string a partir do inverted index do OpenAlex.

    O OpenAlex retorna o abstract como um dicionario onde cada chave é uma palavra
    e o valor é uma lista de posicoes (índices) onde essa palavra aparece no texto.

    Args:
        inverted_index: dicionario {palavra: [posicoes]} ou None.

    Returns:
        String com o abstract reconstruido ou None se nao houver dados.
    """
    if not inverted_index or not isinstance(inverted_index, dict):
        return None

    try:
        # Monta lista de tuplas (posicao, palavra) e ordena por posicao
        position_word_pairs: list[tuple[int, str]] = []
        for word, positions in inverted_index.items():
            for pos in positions:
                position_word_pairs.append((pos, word))

        position_word_pairs.sort(key=lambda pair: pair[0])

        # Reconstrói o texto juntando as palavras na ordem correta
        return " ".join(word for _, word in position_word_pairs)
    except Exception as exc:
        # Em caso de qualquer falha na reconstrucao, retorna None
        logger.warning("Falha ao reconstruir abstract do OpenAlex: %s", exc)
        return None


class OpenAlexClient:
    """
    Cliente HTTP assincrono para OpenAlex.

    Usa o endpoint de works para obter metadados de trabalhos academicos
    e normaliza para o formato interno usado pelo public-indexer.
    """

    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.OPENALEX_BASE_URL.rstrip("/")
        self._max_retries = settings.MAX_RETRIES
        self._timeout = httpx.Timeout(
            connect=10.0,
            read=30.0,
            write=10.0,
            pool=10.0,
        )

    async def search_works(
        self,
        query: str = "",
        limit: int = 100,
        cursor: str = "*",
    ) -> tuple[list[dict[str, Any]], str | None]:
        """
        Busca trabalhos academicos no OpenAlex com paginacao por cursor.

        Args:
            query: termo de busca (vazio para catalogo geral).
            limit: numero maximo de resultados por pagina.
            cursor: cursor de paginacao (padrao '*' para primeira pagina).

        Returns:
            Tupla com lista de dicionarios normalizados e proximo cursor (ou None).
        """
        params: dict[str, Any] = {
            "per_page": limit,
            "cursor": cursor,
        }
        if query:
            params["search"] = query

        raw = await self._request_with_retry("/works", params)
        if not raw or "results" not in raw:
            logger.warning("Resposta vazia ou invalida do OpenAlex")
            return [], None

        next_cursor = raw.get("meta", {}).get("next_cursor")
        results = [
            self._normalize_work(work)
            for work in raw["results"]
            if work.get("title")
        ]

        return results, next_cursor

    async def _request_with_retry(
        self,
        path: str,
        params: dict[str, Any],
    ) -> dict[str, Any] | None:
        """
        Faz requisicao HTTP com retry exponencial para erros transitorios.

        Args:
            path: caminho da URL relativo a base_url.
            params: parametros de query.

        Returns:
            JSON parseado ou None em caso de falha.
        """
        url = f"{self._base_url}{path}"
        last_exc: Exception | None = None

        for attempt in range(1, self._max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.get(url, params=params)
                    response.raise_for_status()
                    return response.json()
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                last_exc = exc
                logger.warning(
                    "Tentativa %d/%d falhou para %s: %s",
                    attempt,
                    self._max_retries,
                    path,
                    exc,
                )
                if attempt < self._max_retries:
                    import asyncio

                    await asyncio.sleep(2 ** (attempt - 1))
            except httpx.HTTPStatusError as exc:
                logger.error(
                    "Erro HTTP %d para %s: %s",
                    exc.response.status_code,
                    path,
                    exc,
                )
                return None

        logger.error(
            "Todas as %d tentativas falharam para %s",
            self._max_retries,
            path,
        )
        raise last_exc or RuntimeError(f"Falha apos {self._max_retries} tentativas")

    @staticmethod
    def _normalize_work(work: dict[str, Any]) -> dict[str, Any]:
        """
        Normaliza trabalho bruto do OpenAlex para formato interno.

        Args:
            work: documento JSON retornado pela API.

        Returns:
            Dicionario com campos normalizados.
        """
        # Extrai source_id do campo 'id' (ex: https://openalex.org/W123456)
        openalex_id = work.get("id", "")
        # Extrai apenas a parte final do ID
        source_id = openalex_id.split("/")[-1] if openalex_id else None

        # Autores: authorships e lista de objetos com author.display_name
        authors = []
        for authorship in work.get("authorships", []):
            author = authorship.get("author", {})
            display_name = author.get("display_name")
            if display_name:
                authors.append(display_name)

        # Assuntos: concepts e lista de objetos com display_name
        subjects = []
        for concept in work.get("concepts", []):
            display_name = concept.get("display_name")
            if display_name:
                subjects.append(display_name)

        # Ano de publicacao
        year = work.get("publication_year")

        # URL de acesso aberto
        url = None
        open_access = work.get("open_access", {})
        if open_access:
            url = open_access.get("oa_url")

        # DOI
        doi = work.get("doi")
        # Remove prefixo https://doi.org/ se presente
        if doi and doi.startswith("https://doi.org/"):
            doi = doi[len("https://doi.org/"):]

        return {
            "source_id": source_id,
            "source_provider": "openalex",
            "title": work.get("title", ""),
            "authors": authors,
            "language": work.get("language"),
            "subjects": subjects,
            "year": year,
            "doi": doi,
            "url": url,
            "abstract": _reconstruct_abstract(work.get("abstract_inverted_index")),  # Converte dict para string
            "source": "openalex",
        }
