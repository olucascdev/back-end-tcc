"""
Cliente assincrono para o Project Gutenberg.

Responsavel por buscar metadados do catalogo RDF e HTML,
normalizar campos e extrair URLs de download por formato.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urljoin

import httpx

from app.core.config import Settings

logger = logging.getLogger(__name__)

# Regex para extrair URLs de download do catalogo HTML Gutenberg
_DOWNLOAD_URL_RE = re.compile(
    r'<a\s+href="([^"]+)"[^>]*>(txt|epub|pdf|html|kindle|mobi)</a>',
    re.IGNORECASE,
)

# Regex para extrair metadados de pagina de livro Gutenberg
_TITLE_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.DOTALL)
_AUTHOR_RE = re.compile(
    r'<a\s+href="/author/[^"]*"[^>]*>(.*?)</a>',
    re.DOTALL,
)
_LANGUAGE_RE = re.compile(r"Language:\s*(\w+)")
_SUBJECT_RE = re.compile(r"Subject:\s*([^\n<]+)")


class GutenbergClient:
    """
    Cliente HTTP assincrono para Project Gutenberg.

    Usa o endpoint de busca e paginas de livro para obter metadados
    e URLs de download.
    """

    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.PROJECT_GUTENBERG_BASE_URL.rstrip("/")
        self._max_retries = settings.MAX_RETRIES
        self._timeout = httpx.Timeout(
            connect=10.0,
            read=30.0,
            write=10.0,
            pool=10.0,
        )

    async def search_books(
        self,
        query: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """
        Busca livros no Project Gutenberg via endpoint de busca.

        Args:
            query: termo de busca (vazio para catalogo geral).
            limit: numero maximo de resultados.
            offset: deslocamento para paginacao.

        Returns:
            Lista de dicionarios com metadados normalizados.
        """
        params = {
            "format": "json",
        }
        if query:
            params["query"] = query

        # Gutenberg nao tem API JSON oficial de busca; usamos o endpoint
        # de busca HTML e parseamos os resultados.
        # Para producao, ideal seria usar o catalogo RDF completo.
        raw_results = await self._fetch_search_results(
            query=query, limit=limit, offset=offset
        )
        return raw_results

    async def fetch_book_page(self, gutenberg_id: str) -> dict[str, Any] | None:
        """
        Busca pagina HTML de um livro especifico e extrai metadados.

        Args:
            gutenberg_id: ID numerico do livro no Gutenberg.

        Returns:
            Dicionario com metadados normalizados ou None.
        """
        path = f"/ebooks/{gutenberg_id}"
        html = await self._request_with_retry(path, accept="text/html")
        if not html:
            return None

        return self._parse_book_page(html, gutenberg_id)

    async def _fetch_search_results(
        self,
        query: str,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        """
        Busca resultados via pagina de busca do Gutenberg.

        Args:
            query: termo de busca.
            limit: maximo de resultados.
            offset: deslocamento.

        Returns:
            Lista de metadados normalizados.
        """
        # Gutenberg usa busca por pagina HTML; extrai IDs dos links
        path = "/ebooks/"
        params: dict[str, Any] = {}
        if query:
            params["query"] = query

        html = await self._request_with_retry(path, params=params, accept="text/html")
        if not html:
            return []

        return self._parse_search_results(html, limit=limit)

    async def _request_with_retry(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        accept: str = "application/json",
    ) -> str | None:
        """
        Faz requisicao HTTP com retry exponencial.

        Args:
            path: caminho relativo a base_url.
            params: parametros de query.
            accept: header Accept.

        Returns:
            Conteudo da resposta como string ou None.
        """
        url = f"{self._base_url}{path}"
        headers = {"Accept": accept}
        last_exc: Exception | None = None

        for attempt in range(1, self._max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.get(url, params=params, headers=headers)
                    response.raise_for_status()
                    return response.text
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
    def _parse_book_page(html: str, gutenberg_id: str) -> dict[str, Any]:
        """
        Parseia pagina HTML de livro Gutenberg e extrai metadados.

        Args:
            html: conteudo HTML da pagina.
            gutenberg_id: ID do livro.

        Returns:
            Dicionario com campos normalizados.
        """
        # Titulo
        title_match = _TITLE_RE.search(html)
        title = title_match.group(1).strip() if title_match else ""

        # Autores
        authors = [m.group(1).strip() for m in _AUTHOR_RE.finditer(html)]

        # Idioma
        lang_match = _LANGUAGE_RE.search(html)
        language = lang_match.group(1).strip() if lang_match else None

        # Assuntos
        subjects = [m.group(1).strip() for m in _SUBJECT_RE.finditer(html)]

        # URLs de download
        download_urls = GutenbergClient._extract_download_urls(html)

        # Formatos disponiveis
        formats = list(download_urls.keys())

        return {
            "gutenberg_id": gutenberg_id,
            "title": title,
            "authors": authors,
            "language": language,
            "subjects": subjects,
            "formats": formats,
            "download_urls": download_urls,
            "source": "gutenberg",
        }

    @staticmethod
    def _parse_search_results(html: str, limit: int = 100) -> list[dict[str, Any]]:
        """
        Parseia pagina de busca do Gutenberg e extrai IDs de livros.

        Args:
            html: conteudo HTML da pagina de busca.
            limit: maximo de resultados.

        Returns:
            Lista de dicionarios com gutenberg_id e titulo basico.
        """
        # Extrai links para paginas de ebooks: /ebooks/12345
        id_pattern = re.compile(r"/ebooks/(\d+)")
        title_pattern = re.compile(r"<li[^>]*>.*?<a[^>]*>(.*?)</a>", re.DOTALL)

        ids = id_pattern.findall(html)
        # Remove duplicatas mantendo ordem
        seen = set()
        unique_ids = []
        for eid in ids:
            if eid not in seen:
                seen.add(eid)
                unique_ids.append(eid)

        results = []
        for eid in unique_ids[:limit]:
            results.append(
                {
                    "gutenberg_id": eid,
                    "title": "",  # Titulo completo obtido via fetch_book_page
                    "authors": [],
                    "language": None,
                    "subjects": [],
                    "formats": [],
                    "download_urls": {},
                    "source": "gutenberg",
                }
            )

        return results

    @staticmethod
    def _extract_download_urls(html: str) -> dict[str, str]:
        """
        Extrai URLs de download por formato da pagina HTML.

        Args:
            html: conteudo HTML da pagina do livro.

        Returns:
            Dicionario formato -> URL absoluta.
        """
        urls: dict[str, str] = {}

        for match in _DOWNLOAD_URL_RE.finditer(html):
            url = match.group(1)
            fmt = match.group(2).lower()
            # Converte URL relativa para absoluta
            abs_url = urljoin("https://www.gutenberg.org", url)
            urls[fmt] = abs_url

        return urls
