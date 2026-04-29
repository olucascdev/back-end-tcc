"""
Casos de uso do public-indexer.

Coordena dominio e infraestrutura para executar operacoes de indexacao.
"""

from __future__ import annotations

import logging
import time
from typing import Optional
from uuid import UUID

from app.application.artifact_processor import ArtifactProcessorUseCase
from app.application.embedding_processor import EmbeddingProcessorUseCase
from app.core import metrics
from app.domain.models import BookMetadata, IndexerJob, JobStatus
from app.domain.services import BookCatalogService, JobStore
from app.infrastructure.dlq import FailureTracker
from app.application.job_reporter import JobReporter

logger = logging.getLogger(__name__)


class RunIndexUseCase:
    """
    Caso de uso para executar indexacao de acervo publico.

    Orquestra:
    1. Criacao de job
    2. Busca de livros pendentes no MongoDB
    3. Download e armazenamento de artefatos (Feature 5.3)
    4. Geracao de embeddings (Feature 5.4)
    5. Atualizacao de status
    """

    def __init__(
        self,
        book_catalog: BookCatalogService,
        job_store: JobStore,
        artifact_processor: ArtifactProcessorUseCase,
        embedding_processor: EmbeddingProcessorUseCase,
        failure_tracker: Optional[FailureTracker] = None,
        job_reporter: Optional[JobReporter] = None,
    ) -> None:
        self._book_catalog = book_catalog
        self._job_store = job_store
        self._artifact_processor = artifact_processor
        self._embedding_processor = embedding_processor
        self._failure_tracker = failure_tracker
        self._job_reporter = job_reporter

    async def execute(
        self,
        source_filter: Optional[str] = None,
        dry_run: bool = False,
    ) -> IndexerJob:
        """
        Executa pipeline de indexacao.

        Args:
            source_filter: filtro opcional de fonte (ex: 'gutenberg').
            dry_run: se True, apenas simula sem persistir embeddings.

        Returns:
            Job com status atualizado.
        """
        job = IndexerJob(
            source_filter=source_filter,
            dry_run=dry_run,
        )
        self._job_store.create(job)
        job.mark_running()
        self._job_store.update(job)

        start_time = time.perf_counter()

        # Metricas: inicio da execucao
        metrics.public_indexer_runs_total.labels(
            status="started",
            source_filter=source_filter or "all",
        ).inc()

        try:
            # Busca livros pendentes
            pending_books = await self._book_catalog.get_pending_books(
                limit=100  # TODO: usar settings.BATCH_SIZE
            )

            books_fetched = len(pending_books)

            # Metricas: livros buscados
            for book_doc in pending_books:
                provider = self._extract_provider(book_doc.get("stable_key", ""))
                metrics.public_books_fetched_total.labels(
                    source_provider=provider,
                ).inc()

            if dry_run:
                logger.info(
                    "Dry run: %d livros pendentes encontrados, nenhum processado",
                    books_fetched,
                )
                job.mark_completed(items_processed=0)
                self._job_store.update(job)
                self._emit_completion_metrics(job, start_time, source_filter)
                return job

            # Processa cada livro
            processed = 0
            embedded = 0
            failed = 0
            skipped = 0
            failures_by_stage: dict[str, int] = {}

            for book_doc in pending_books:
                stable_key = book_doc.get("stable_key", "")
                provider = self._extract_provider(stable_key)

                try:
                    # Converte documento MongoDB para BookMetadata
                    book = BookMetadata(
                        gutenberg_id=book_doc.get("gutenberg_id"),
                        ol_key=book_doc.get("ol_key"),
                        title=book_doc.get("title", ""),
                        authors=book_doc.get("authors", []),
                        language=book_doc.get("language"),
                        subjects=book_doc.get("subjects", []),
                        year=book_doc.get("year"),
                        checksum=book_doc.get("checksum"),
                    )

                    artifact_success = False
                    artifact_skipped = False

                    # Processa artefato (download + MinIO + MongoDB update)
                    artifact_result = await self._artifact_processor.execute(book)
                    if artifact_result.success:
                        artifact_success = True
                        artifact_skipped = artifact_result.skipped
                    else:
                        failed += 1
                        failures_by_stage["artifact_download"] = (
                            failures_by_stage.get("artifact_download", 0) + 1
                        )
                        metrics.public_indexer_failures_total.labels(
                            stage="artifact_download",
                            source_provider=provider,
                        ).inc()
                        # Registra falha permanente
                        await self._record_failure(
                            stable_key,
                            artifact_result.error or "Unknown error",
                            provider,
                        )
                        continue

                    # Se artefato foi skipado mas embeddings nao existem,
                    # ainda executa embedding processor
                    should_embed = True
                    if artifact_skipped:
                        # Artefato skipado: verifica se embeddings existem
                        # Se ja tem embedding_count no MongoDB, skipa embedding tambem
                        existing = await self._book_catalog.find_by_stable_key(
                            stable_key
                        )
                        if existing and existing.get("embedding_count", 0) > 0:
                            should_embed = False
                            skipped += 1

                    # Processa embeddings
                    if should_embed:
                        embed_result = await self._embedding_processor.execute(
                            book=book,
                            artifact_key=artifact_result.artifact_key or "",
                            checksum=artifact_result.checksum or "",
                        )

                        if embed_result.success:
                            if embed_result.skipped:
                                skipped += 1
                            else:
                                embedded += 1
                                metrics.public_embeddings_generated_total.labels(
                                    source_provider=provider,
                                ).inc(embed_result.chunks_count)
                        else:
                            failed += 1
                            failures_by_stage["embedding"] = (
                                failures_by_stage.get("embedding", 0) + 1
                            )
                            metrics.public_indexer_failures_total.labels(
                                stage="embedding",
                                source_provider=provider,
                            ).inc()
                            await self._record_failure(
                                stable_key,
                                embed_result.error or "Unknown embedding error",
                                provider,
                            )
                            continue

                    # Marca como indexado apos SUCESSO de artefato E embedding
                    if artifact_success:
                        await self._book_catalog.mark_indexed(stable_key)
                        processed += 1
                        metrics.public_books_indexed_total.labels(
                            source_provider=provider,
                        ).inc()

                except Exception as exc:
                    # Isola falhas por livro — loga e continua
                    failed += 1
                    stage = "unknown"
                    failures_by_stage[stage] = failures_by_stage.get(stage, 0) + 1
                    metrics.public_indexer_failures_total.labels(
                        stage=stage,
                        source_provider=provider,
                    ).inc()
                    logger.error(
                        "Erro isolado ao processar livro: stable_key=%s, erro=%s",
                        stable_key,
                        exc,
                    )
                    await self._record_failure(stable_key, str(exc), provider)

            job.mark_completed(items_processed=processed)
            self._job_store.update(job)

            logger.info(
                "Indexacao concluida: job_id=%s, processados=%d, embedded=%d, falhas=%d, skipados=%d",
                job.job_id,
                processed,
                embedded,
                failed,
                skipped,
            )

            # Gera e loga relatorio
            await self._generate_report(
                job=job,
                start_time=start_time,
                books_fetched=books_fetched,
                books_processed=processed,
                books_embedded=embedded,
                books_failed=failed,
                books_skipped=skipped,
                failures_by_stage=failures_by_stage,
                source_filter=source_filter,
            )

        except Exception as exc:
            job.mark_failed(str(exc))
            self._job_store.update(job)
            logger.error("Job falhou: job_id=%s, erro=%s", job.job_id, exc)

            metrics.public_indexer_runs_total.labels(
                status="failed",
                source_filter=source_filter or "all",
            ).inc()

            raise

        return job

    def _emit_completion_metrics(
        self,
        job: IndexerJob,
        start_time: float,
        source_filter: Optional[str],
    ) -> None:
        """Emite metricas de conclusao do job."""
        duration = time.perf_counter() - start_time
        status = "completed" if job.status == JobStatus.COMPLETED else "failed"

        metrics.public_indexer_runs_total.labels(
            status=status,
            source_filter=source_filter or "all",
        ).inc()

        metrics.public_indexer_run_duration_seconds.labels(
            status=status,
        ).observe(duration)

    async def _generate_report(
        self,
        job: IndexerJob,
        start_time: float,
        books_fetched: int,
        books_processed: int,
        books_embedded: int,
        books_failed: int,
        books_skipped: int,
        failures_by_stage: dict[str, int],
        source_filter: Optional[str],
    ) -> None:
        """Gera relatorio final do job."""
        duration = time.perf_counter() - start_time

        if self._job_reporter:
            report = self._job_reporter.create_report(
                job_id=job.job_id,
                status=job.status.value,
                started_at=job.started_at,
                completed_at=job.completed_at,
                books_fetched=books_fetched,
                books_processed=books_processed,
                books_embedded=books_embedded,
                books_failed=books_failed,
                books_skipped=books_skipped,
                failures_by_stage=failures_by_stage,
                duration_seconds=duration,
                source_filter=source_filter,
            )
            self._job_reporter.log_report(report)
            await self._job_reporter.store_report(report)

        # Emite metricas de conclusao
        self._emit_completion_metrics(job, start_time, source_filter)

    async def _record_failure(
        self,
        stable_key: str,
        error: str,
        source_provider: str,
    ) -> None:
        """Registra falha permanente no failure tracker."""
        if self._failure_tracker:
            try:
                await self._failure_tracker.record_failure(
                    stable_key=stable_key,
                    error=error,
                    source_provider=source_provider,
                )
            except Exception as exc:
                logger.warning("Falha ao registrar falha: %s", exc)

    @staticmethod
    def _extract_provider(stable_key: str) -> str:
        """Extrai provider do stable_key."""
        if ":" in stable_key:
            return stable_key.split(":")[0]
        return "unknown"


class GetJobStatusUseCase:
    """
    Caso de uso para consultar status de job de indexacao.
    """

    def __init__(self, job_store: JobStore) -> None:
        self._job_store = job_store

    def execute(self, job_id: UUID) -> Optional[IndexerJob]:
        """
        Retorna status do job.

        Args:
            job_id: identificador do job.

        Returns:
            Job ou None se nao encontrado.
        """
        return self._job_store.get(job_id)
