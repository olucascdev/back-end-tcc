"""
Gerador de relatorios de jobs de indexacao.

Produz relatorio estruturado ao final de cada execucao
e opcionalmente armazena no MongoDB.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Optional
from uuid import UUID

logger = logging.getLogger(__name__)


@dataclass
class JobReport:
    """Relatorio de execucao de job de indexacao."""

    job_id: str
    status: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    books_fetched: int = 0
    books_processed: int = 0
    books_embedded: int = 0
    books_failed: int = 0
    books_skipped: int = 0
    failures_by_stage: dict[str, int] = field(default_factory=dict)
    duration_seconds: float = 0.0
    source_filter: Optional[str] = None

    def to_dict(self) -> dict:
        """Converte para dict para serializacao."""
        return {
            "job_id": self.job_id,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "books_fetched": self.books_fetched,
            "books_processed": self.books_processed,
            "books_embedded": self.books_embedded,
            "books_failed": self.books_failed,
            "books_skipped": self.books_skipped,
            "failures_by_stage": self.failures_by_stage,
            "duration_seconds": round(self.duration_seconds, 2),
            "source_filter": self.source_filter,
        }

    def to_json(self) -> str:
        """Converte para JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


class JobReporter:
    """
    Gera e armazena relatorios de jobs de indexacao.

    Opcionalmente persiste no MongoDB para historico.
    """

    COLLECTION_NAME = "job_reports"

    def __init__(self, mongo_db=None) -> None:
        """
        Inicializa reporter.

        Args:
            mongo_db: instancia motor database. Se None, nao persiste.
        """
        self._db = mongo_db
        self._collection = None
        if mongo_db is not None:
            self._collection = mongo_db.get_collection(self.COLLECTION_NAME)

    def create_report(
        self,
        job_id: UUID,
        status: str,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        books_fetched: int = 0,
        books_processed: int = 0,
        books_embedded: int = 0,
        books_failed: int = 0,
        books_skipped: int = 0,
        failures_by_stage: Optional[dict[str, int]] = None,
        duration_seconds: float = 0.0,
        source_filter: Optional[str] = None,
    ) -> JobReport:
        """
        Cria relatorio de job.

        Args:
            job_id: identificador do job.
            status: status final do job.
            started_at: timestamp de inicio.
            completed_at: timestamp de conclusao.
            books_fetched: livros buscados do catalogo.
            books_processed: livros processados com sucesso.
            books_embedded: livros com embeddings gerados.
            books_failed: livros que falharam.
            books_skipped: livros skipados (idempotencia).
            failures_by_stage: contagem de falhas por estagio.
            duration_seconds: duracao total em segundos.
            source_filter: filtro de fonte aplicado.

        Returns:
            JobReport criado.
        """
        report = JobReport(
            job_id=str(job_id),
            status=status,
            started_at=started_at.isoformat() if started_at else None,
            completed_at=completed_at.isoformat() if completed_at else None,
            books_fetched=books_fetched,
            books_processed=books_processed,
            books_embedded=books_embedded,
            books_failed=books_failed,
            books_skipped=books_skipped,
            failures_by_stage=failures_by_stage or {},
            duration_seconds=duration_seconds,
            source_filter=source_filter,
        )

        return report

    async def store_report(self, report: JobReport) -> None:
        """
        Armazena relatorio no MongoDB.

        Args:
            report: relatorio a armazenar.
        """
        if self._collection is None:
            logger.debug("MongoDB nao configurado, relatorio nao persistido")
            return

        try:
            doc = report.to_dict()
            doc["created_at"] = datetime.now(UTC)
            await self._collection.insert_one(doc)
            logger.info("Relatorio armazenado: job_id=%s", report.job_id)
        except Exception as exc:
            logger.warning("Falha ao armazenar relatorio: %s", exc)

    def log_report(self, report: JobReport) -> None:
        """
        Loga relatorio como JSON estruturado.

        Args:
            report: relatorio a logar.
        """
        logger.info(
            "Job report: %s",
            report.to_json(),
        )
