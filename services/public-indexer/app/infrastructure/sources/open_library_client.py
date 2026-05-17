"""
Cliente assincrono para a API do Open Library.

Responsavel por buscar metadados de livros via endpoint de busca,
normalizar campos e lidar com paginacao e retries.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import Settings

logger = logging.getLogger(__name__)


class OpenLibraryClient:
    """
    Cliente HTTP assincrono para Open Library.

    Usa o endpoint de busca (search) para obter metadados de livros
    e normaliza para o formato interno BookMetadata.
    """

    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.OPEN_LIBRARY_BASE_URL.rstrip("/")
        self._max_retries = settings.MAX_RETRIES
        self._timeout = httpx.Timeout(
            connect=10.0,
            read=30.0,
            write=10.0,
            pool=10.0,
        )

    async def search_books(
        self,
        query: str = "*",
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """
        Busca livros no Open Library com paginacao.

        Args:
            query: termo de busca (padrao '*' para todos).
            limit: numero maximo de resultados por pagina.
            offset: deslocamento para paginacao.

        Returns:
            Lista de dicionarios com metadados normalizados.
        """
        params = {
            "q": query,
            "limit": limit,
            "offset": offset,
            "fields": "key,title,author_name,language,subject,first_publish_year,format",
        }

        raw = await self._request_with_retry("/search.json", params)
        if not raw or "docs" not in raw:
            logger.warning("Resposta vazia ou invalida do Open Library")
            return []

        return [self._normalize_doc(doc) for doc in raw["docs"] if doc.get("title")]

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
                    # Backoff exponencial: 1s, 2s, 4s...
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
    def _normalize_doc(doc: dict[str, Any]) -> dict[str, Any]:
        """
        Normaliza documento bruto do Open Library para formato interno.

        Args:
            doc: documento JSON retornado pela API.

        Returns:
            Dicionario com campos normalizados.
        """
        # Extrai ol_key do campo 'key' (ex: /works/OL123W)
        raw_key = doc.get("key", "")
        ol_key = raw_key if raw_key.startswith("/works/") else None

        # Autores: author_name e lista de strings
        authors = doc.get("author_name", [])
        if isinstance(authors, str):
            authors = [authors]

        # Idioma: language e lista, pega o primeiro
        languages = doc.get("language", [])
        language = languages[0] if languages else None

        # Assuntos: subject e lista de strings
        subjects = doc.get("subject", [])
        if isinstance(subjects, str):
            subjects = [subjects]

        # Formatos: field pode nao existir
        formats = doc.get("format", [])
        if isinstance(formats, str):
            formats = [formats]

        return {
            "ol_key": ol_key,
            "title": doc.get("title", ""),
            "authors": authors,
            "language": language,
            "subjects": subjects,
            "year": doc.get("first_publish_year"),
            "formats": formats,
            "source": "openlibrary",
        }
