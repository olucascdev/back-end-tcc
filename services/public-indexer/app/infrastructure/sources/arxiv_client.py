"""
Cliente assincrono para a API arXiv.

Responsavel por buscar metadados de artigos academicos via API Atom/XML,
parsear o feed, normalizar campos e lidar com paginacao e retries.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import urljoin

import httpx

from app.core.config import Settings

logger = logging.getLogger(__name__)

# Namespace Atom usado pelo arXiv
ATOM_NS = "http://www.w3.org/2005/Atom"
ARXIV_NS = "http://arxiv.org/schemas/atom"


class ArxivClient:
    """
    Cliente HTTP assincrono para arXiv.

    Usa o endpoint de query para obter metadados de artigos academicos
    e normaliza para o formato interno usado pelo public-indexer.
    """

    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.ARXIV_BASE_URL.rstrip("/")
        self._max_retries = settings.MAX_RETRIES
        self._timeout = httpx.Timeout(
            connect=10.0,
            read=30.0,
            write=10.0,
            pool=10.0,
        )

    async def search_papers(
        self,
        query: str = "",
        limit: int = 100,
        start: int = 0,
    ) -> list[dict[str, Any]]:
        """
        Busca artigos no arXiv com paginacao por offset.

        Args:
            query: termo de busca (vazio para catalogo geral).
            limit: numero maximo de resultados por pagina.
            start: deslocamento para paginacao.

        Returns:
            Lista de dicionarios com metadados normalizados.
        """
        params = {
            "search_query": query if query else "all",
            "start": start,
            "max_results": limit,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }

        xml_content = await self._request_with_retry("/api/query", params)
        if not xml_content:
            logger.warning("Resposta vazia ou invalida do arXiv")
            return []

        return self._parse_feed(xml_content)

    async def _request_with_retry(
        self,
        path: str,
        params: dict[str, Any],
    ) -> str | None:
        """
        Faz requisicao HTTP com retry exponencial para erros transitorios.

        Args:
            path: caminho da URL relativo a base_url.
            params: parametros de query.

        Returns:
            Conteudo XML da resposta como string ou None em caso de falha.
        """
        url = f"{self._base_url}{path}"
        last_exc: Exception | None = None

        for attempt in range(1, self._max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.get(url, params=params)
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

    def _parse_feed(self, xml_content: str) -> list[dict[str, Any]]:
        """
        Parseia feed Atom/XML do arXiv e extrai metadados dos artigos.

        Args:
            xml_content: conteudo XML do feed.

        Returns:
            Lista de dicionarios com campos normalizados.
        """
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as exc:
            logger.error("Erro ao parsear XML do arXiv: %s", exc)
            return []

        namespaces = {
            "atom": ATOM_NS,
            "arxiv": ARXIV_NS,
        }

        entries = root.findall("atom:entry", namespaces)
        results = []

        for entry in entries:
            result = self._parse_entry(entry, namespaces)
            if result:
                results.append(result)

        return results

    def _parse_entry(
        self,
        entry: ET.Element,
        namespaces: dict[str, str],
    ) -> dict[str, Any] | None:
        """
        Parseia uma entrada (entry) do feed Atom e extrai metadados.

        Args:
            entry: elemento XML da entrada.
            namespaces: mapeamento de namespaces XML.

        Returns:
            Dicionario com campos normalizados ou None.
        """
        # Titulo
        title_elem = entry.find("atom:title", namespaces)
        title = title_elem.text.strip() if title_elem is not None and title_elem.text else ""
        if not title:
            return None

        # ID do arXiv (ex: http://arxiv.org/abs/2101.12345v1)
        id_elem = entry.find("atom:id", namespaces)
        raw_id = id_elem.text.strip() if id_elem is not None and id_elem.text else ""
        # Extrai o ID do arXiv (ex: 2101.12345v1)
        arxiv_id = raw_id.split("/")[-1] if raw_id else ""
        # Remove versao para source_id estavel (ex: 2101.12345)
        source_id = arxiv_id.split("v")[0] if arxiv_id else ""

        # Autores
        authors = []
        for author_elem in entry.findall("atom:author", namespaces):
            name_elem = author_elem.find("atom:name", namespaces)
            if name_elem is not None and name_elem.text:
                authors.append(name_elem.text.strip())

        # Resumo (summary)
        summary_elem = entry.find("atom:summary", namespaces)
        summary = summary_elem.text.strip() if summary_elem is not None and summary_elem.text else ""

        # Data de publicacao (published)
        published_elem = entry.find("atom:published", namespaces)
        year = None
        if published_elem is not None and published_elem.text:
            try:
                year = int(published_elem.text[:4])
            except (ValueError, TypeError):
                pass

        # Tags/categorias como subjects
        subjects = []
        for category_elem in entry.findall("atom:category", namespaces):
            term = category_elem.get("term")
            if term:
                subjects.append(term)

        # URL do PDF
        pdf_url = None
        for link_elem in entry.findall("atom:link", namespaces):
            link_type = link_elem.get("type", "")
            if link_type == "application/pdf":
                pdf_url = link_elem.get("href")
                break

        # Se nao encontrou link PDF explicito, constroi URL padrao
        if not pdf_url and source_id:
            pdf_url = f"https://arxiv.org/pdf/{source_id}.pdf"

        return {
            "source_id": source_id,
            "source_provider": "arxiv",
            "title": title,
            "authors": authors,
            "language": None,  # arXiv nao fornece idioma explicitamente
            "subjects": subjects,
            "year": year,
            "abstract": summary if summary else None,
            "url": pdf_url,
            "source": "arxiv",
        }
