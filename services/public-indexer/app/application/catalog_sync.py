"""
Caso de uso para sincronizacao de catalogo de fontes externas.

Coordena busca de metadados no Open Library, Project Gutenberg,
OpenAlex, arXiv e Crossref, deduplica por stable_key e persiste no MongoDB.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from app.core import metrics
from app.domain.models import BookMetadata
from app.domain.services import BookCatalogService
from app.infrastructure.sources.arxiv_client import ArxivClient
from app.infrastructure.sources.crossref_client import CrossrefClient
from app.infrastructure.sources.gutenberg_client import GutenbergClient
from app.infrastructure.sources.open_library_client import OpenLibraryClient
from app.infrastructure.sources.openalex_client import OpenAlexClient

logger = logging.getLogger(__name__)


@dataclass
class SyncReport:
    """Relatorio de sincronizacao de catalogo."""

    new: int = 0
    updated: int = 0
    unchanged: int = 0
    errors: int = 0
    source: str = ""
    details: list[str] = field(default_factory=list)


class CatalogSyncUseCase:
    """
    Caso de uso para sincronizar catalogo de fontes externas.

    Busca livros de cada fonte, normaliza para BookMetadata,
    deduplica por stable_key e faz upsert no MongoDB.
    """

    def __init__(
        self,
        book_catalog: BookCatalogService,
        open_library_client: OpenLibraryClient,
        gutenberg_client: GutenbergClient,
        openalex_client: Optional[OpenAlexClient] = None,
        arxiv_client: Optional[ArxivClient] = None,
        crossref_client: Optional[CrossrefClient] = None,
        batch_size: int = 100,
    ) -> None:
        self._book_catalog = book_catalog
        self._open_library = open_library_client
        self._gutenberg = gutenberg_client
        self._openalex = openalex_client
        self._arxiv = arxiv_client
        self._crossref = crossref_client
        self._batch_size = batch_size

    async def execute(
        self,
        source_filter: Optional[str] = None,
    ) -> dict[str, SyncReport]:
        """
        Executa sincronizacao de catalogo.

        Args:
            source_filter: filtro de fonte ('gutenberg', 'openlibrary',
                'openalex', 'arxiv', 'crossref', ou None para todas).

        Returns:
            Dicionario com relatorio por fonte.
        """
        reports: dict[str, SyncReport] = {}

        sources_to_run = []
        if source_filter is None or source_filter == "openlibrary":
            sources_to_run.append(("openlibrary", self._sync_open_library))
        if source_filter is None or source_filter == "gutenberg":
            sources_to_run.append(("gutenberg", self._sync_gutenberg))
        if source_filter is None or source_filter == "openalex":
            if self._openalex:
                sources_to_run.append(("openalex", self._sync_openalex))
            else:
                logger.warning("Fonte openalex solicitada mas cliente nao configurado")
                reports["openalex"] = SyncReport(
                    source="openalex",
                    errors=1,
                    details=["Cliente OpenAlex nao configurado"],
                )
        if source_filter is None or source_filter == "arxiv":
            if self._arxiv:
                sources_to_run.append(("arxiv", self._sync_arxiv))
            else:
                logger.warning("Fonte arxiv solicitada mas cliente nao configurado")
                reports["arxiv"] = SyncReport(
                    source="arxiv",
                    errors=1,
                    details=["Cliente arXiv nao configurado"],
                )
        if source_filter is None or source_filter == "crossref":
            if self._crossref:
                sources_to_run.append(("crossref", self._sync_crossref))
            else:
                logger.warning("Fonte crossref solicitada mas cliente nao configurado")
                reports["crossref"] = SyncReport(
                    source="crossref",
                    errors=1,
                    details=["Cliente Crossref nao configurado"],
                )

        for source_name, sync_fn in sources_to_run:
            logger.info("Iniciando sincronizacao da fonte: %s", source_name)
            try:
                report = await sync_fn()
                report.source = source_name
                reports[source_name] = report
                logger.info(
                    "Sincronizacao %s concluida: new=%d, updated=%d, unchanged=%d, errors=%d",
                    source_name,
                    report.new,
                    report.updated,
                    report.unchanged,
                    report.errors,
                )
            except Exception as exc:
                logger.error("Falha na sincronizacao de %s: %s", source_name, exc)
                reports[source_name] = SyncReport(
                    source=source_name,
                    errors=1,
                    details=[f"Falha na sincronizacao: {exc}"],
                )

        return reports

    async def _sync_open_library(self) -> SyncReport:
        """
        Sincroniza livros do Open Library.

        Returns:
            Relatorio de sincronizacao.
        """
        report = SyncReport()
        offset = 0

        while True:
            docs = await self._open_library.search_books(
                limit=self._batch_size,
                offset=offset,
            )

            if not docs:
                break

            for doc in docs:
                try:
                    book = BookMetadata(
                        ol_key=doc.get("ol_key"),
                        title=doc["title"],
                        authors=doc.get("authors", []),
                        language=doc.get("language"),
                        subjects=doc.get("subjects", []),
                        year=doc.get("year"),
                    )
                    result = await self._book_catalog.upsert_book(book)
                    if result.get("upserted"):
                        report.new += 1
                    elif result.get("modified"):
                        report.updated += 1
                    else:
                        report.unchanged += 1
                    # Metricas: livro buscado do Open Library
                    metrics.public_books_fetched_total.labels(
                        source_provider="openlibrary",
                    ).inc()
                except Exception as exc:
                    report.errors += 1
                    logger.warning("Erro ao processar livro Open Library: %s", exc)

            if len(docs) < self._batch_size:
                break

            offset += self._batch_size

        return report

    async def _sync_gutenberg(self) -> SyncReport:
        """
        Sincroniza livros do Project Gutenberg.

        Returns:
            Relatorio de sincronizacao.
        """
        report = SyncReport()

        # Busca lista de IDs do Gutenberg
        search_results = await self._gutenberg.search_books(limit=self._batch_size)

        for result in search_results:
            try:
                gutenberg_id = result.get("gutenberg_id")
                if not gutenberg_id:
                    continue

                # Busca pagina detalhada do livro para metadados completos
                book_data = await self._gutenberg.fetch_book_page(gutenberg_id)
                if not book_data:
                    report.errors += 1
                    continue

                book = BookMetadata(
                    gutenberg_id=book_data["gutenberg_id"],
                    title=book_data.get("title", ""),
                    authors=book_data.get("authors", []),
                    language=book_data.get("language"),
                    subjects=book_data.get("subjects", []),
                )
                result_upsert = await self._book_catalog.upsert_book(book)
                if result_upsert.get("upserted"):
                    report.new += 1
                elif result_upsert.get("modified"):
                    report.updated += 1
                else:
                    report.unchanged += 1
                # Metricas: livro buscado do Gutenberg
                metrics.public_books_fetched_total.labels(
                    source_provider="gutenberg",
                ).inc()
            except Exception as exc:
                report.errors += 1
                logger.warning("Erro ao processar livro Gutenberg: %s", exc)

        return report

    async def _sync_openalex(self) -> SyncReport:
        """
        Sincroniza trabalhos academicos do OpenAlex.

        Returns:
            Relatorio de sincronizacao.
        """
        if not self._openalex:
            return SyncReport(errors=1, details=["Cliente OpenAlex nao configurado"])

        report = SyncReport()
        cursor = "*"

        while True:
            docs, next_cursor = await self._openalex.search_works(
                limit=self._batch_size,
                cursor=cursor,
            )

            if not docs:
                break

            for doc in docs:
                try:
                    book = BookMetadata(
                        source_id=doc.get("source_id"),
                        source_provider=doc.get("source_provider", "openalex"),
                        title=doc["title"],
                        authors=doc.get("authors", []),
                        language=doc.get("language"),
                        subjects=doc.get("subjects", []),
                        year=doc.get("year"),
                        doi=doc.get("doi"),
                        url=doc.get("url"),
                        abstract=doc.get("abstract"),
                    )
                    result = await self._book_catalog.upsert_book(book)
                    if result.get("upserted"):
                        report.new += 1
                    elif result.get("modified"):
                        report.updated += 1
                    else:
                        report.unchanged += 1
                    # Metricas: trabalho buscado do OpenAlex
                    metrics.public_books_fetched_total.labels(
                        source_provider="openalex",
                    ).inc()
                except Exception as exc:
                    report.errors += 1
                    logger.warning("Erro ao processar trabalho OpenAlex: %s", exc)

            if len(docs) < self._batch_size or not next_cursor:
                break

            cursor = next_cursor

        return report

    async def _sync_arxiv(self) -> SyncReport:
        """
        Sincroniza artigos do arXiv.

        Returns:
            Relatorio de sincronizacao.
        """
        if not self._arxiv:
            return SyncReport(errors=1, details=["Cliente arXiv nao configurado"])

        report = SyncReport()
        start = 0

        while True:
            docs = await self._arxiv.search_papers(
                limit=self._batch_size,
                start=start,
            )

            if not docs:
                break

            for doc in docs:
                try:
                    book = BookMetadata(
                        source_id=doc.get("source_id"),
                        source_provider=doc.get("source_provider", "arxiv"),
                        title=doc["title"],
                        authors=doc.get("authors", []),
                        language=doc.get("language"),
                        subjects=doc.get("subjects", []),
                        year=doc.get("year"),
                        url=doc.get("url"),
                        abstract=doc.get("abstract"),
                    )
                    result = await self._book_catalog.upsert_book(book)
                    if result.get("upserted"):
                        report.new += 1
                    elif result.get("modified"):
                        report.updated += 1
                    else:
                        report.unchanged += 1
                    # Metricas: artigo buscado do arXiv
                    metrics.public_books_fetched_total.labels(
                        source_provider="arxiv",
                    ).inc()
                except Exception as exc:
                    report.errors += 1
                    logger.warning("Erro ao processar artigo arXiv: %s", exc)

            if len(docs) < self._batch_size:
                break

            start += self._batch_size

        return report

    async def _sync_crossref(self) -> SyncReport:
        """
        Sincroniza trabalhos academicos do Crossref.

        Returns:
            Relatorio de sincronizacao.
        """
        if not self._crossref:
            return SyncReport(errors=1, details=["Cliente Crossref nao configurado"])

        report = SyncReport()
        offset = 0

        while True:
            docs = await self._crossref.search_works(
                limit=self._batch_size,
                offset=offset,
            )

            if not docs:
                break

            for doc in docs:
                try:
                    book = BookMetadata(
                        source_id=doc.get("source_id"),
                        source_provider=doc.get("source_provider", "crossref"),
                        title=doc["title"],
                        authors=doc.get("authors", []),
                        language=doc.get("language"),
                        subjects=doc.get("subjects", []),
                        year=doc.get("year"),
                        doi=doc.get("doi"),
                        url=doc.get("url"),
                        abstract=doc.get("abstract"),
                    )
                    result = await self._book_catalog.upsert_book(book)
                    if result.get("upserted"):
                        report.new += 1
                    elif result.get("modified"):
                        report.updated += 1
                    else:
                        report.unchanged += 1
                    # Metricas: trabalho buscado do Crossref
                    metrics.public_books_fetched_total.labels(
                        source_provider="crossref",
                    ).inc()
                except Exception as exc:
                    report.errors += 1
                    logger.warning("Erro ao processar trabalho Crossref: %s", exc)

            if len(docs) < self._batch_size:
                break

            offset += self._batch_size

        return report
