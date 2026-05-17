"""
Cliente assincrono para a API Crossref.

Responsavel por buscar metadados de trabalhos academicos via API REST JSON,
normalizar campos e lidar com paginacao e retries.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import Settings

logger = logging.getLogger(__name__)


class CrossrefClient:
    """
    Cliente HTTP assincrono para Crossref.

    Usa o endpoint de works para obter metadados de trabalhos academicos
    e normaliza para o formato interno usado pelo public-indexer.
    """

    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.CROSSREF_BASE_URL.rstrip("/")
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
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """
        Busca trabalhos academicos no Crossref com paginacao por offset.

        Args:
            query: termo de busca (vazio para catalogo geral).
            limit: numero maximo de resultados por pagina.
            offset: deslocamento para paginacao.

        Returns:
            Lista de dicionarios com metadados normalizados.
        """
        params: dict[str, Any] = {
            "rows": limit,
            "offset": offset,
        }
        if query:
            params["query"] = query

        raw = await self._request_with_retry("/works", params)
        if not raw:
            logger.warning("Resposta vazia ou invalida do Crossref")
            return []

        message = raw.get("message", {})
        items = message.get("items", [])

        return [
            self._normalize_work(item)
            for item in items
            if item.get("title")
        ]

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
        Normaliza trabalho bruto do Crossref para formato interno.

        Args:
            work: documento JSON retornado pela API.

        Returns:
            Dicionario com campos normalizados.
        """
        # DOI como source_id
        doi = work.get("DOI", "")
        source_id = doi if doi else None

        # Titulo: pode ser lista
        titles = work.get("title", [])
        title = titles[0] if titles else ""

        # Autores
        authors = []
        for author in work.get("author", []):
            given = author.get("given", "")
            family = author.get("family", "")
            name = f"{given} {family}".strip()
            if name:
                authors.append(name)

        # Assuntos (subject)
        subjects = work.get("subject", [])
        if isinstance(subjects, str):
            subjects = [subjects]

        # Ano de publicacao: tenta published-print, depois published-online, depois created
        year = CrossrefClient._extract_year(work)

        # URL
        url = work.get("URL")

        # Links para PDF
        pdf_url = None
        for link in work.get("link", []):
            if link.get("content-type", "") == "application/pdf":
                pdf_url = link.get("URL")
                break

        # Abstract
        abstract = work.get("abstract")

        return {
            "source_id": source_id,
            "source_provider": "crossref",
            "title": title,
            "authors": authors,
            "language": work.get("language"),
            "subjects": subjects,
            "year": year,
            "doi": doi,
            "url": pdf_url or url,
            "abstract": abstract,
            "source": "crossref",
        }

    @staticmethod
    def _extract_year(work: dict[str, Any]) -> int | None:
        """
        Extrai ano de publicacao de diferentes campos do Crossref.

        Tenta na ordem: published-print, published-online, created.

        Args:
            work: documento JSON do Crossref.

        Returns:
            Ano de publicacao ou None.
        """
        for field in ("published-print", "published-online", "created"):
            date_obj = work.get(field, {})
            date_parts = date_obj.get("date-parts", [])
            if date_parts and date_parts[0]:
                try:
                    return int(date_parts[0][0])
                except (ValueError, TypeError, IndexError):
                    continue
        return None
