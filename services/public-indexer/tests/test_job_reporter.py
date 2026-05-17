"""
Testes do JobReporter.

Verifica geracao, logging e armazenamento de relatorios de jobs.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.application.job_reporter import JobReporter, JobReport


class TestJobReportCreation:
    """Testes de criacao de relatorios."""

    def test_create_minimal_report(self) -> None:
        """Verifica criacao de relatorio minimo."""
        reporter = JobReporter()
        job_id = uuid4()

        report = reporter.create_report(
            job_id=job_id,
            status="completed",
        )

        assert report.job_id == str(job_id)
        assert report.status == "completed"
        assert report.books_fetched == 0
        assert report.books_processed == 0
        assert report.books_embedded == 0
        assert report.books_failed == 0

    def test_create_full_report(self) -> None:
        """Verifica criacao de relatorio completo."""
        reporter = JobReporter()
        job_id = uuid4()
        now = datetime.now(UTC)

        report = reporter.create_report(
            job_id=job_id,
            status="completed",
            started_at=now,
            completed_at=now,
            books_fetched=100,
            books_processed=95,
            books_embedded=90,
            books_failed=5,
            books_skipped=3,
            failures_by_stage={"embedding": 3, "artifact_download": 2},
            duration_seconds=120.5,
            source_filter="gutenberg",
        )

        assert report.books_fetched == 100
        assert report.books_processed == 95
        assert report.books_embedded == 90
        assert report.books_failed == 5
        assert report.books_skipped == 3
        assert report.failures_by_stage["embedding"] == 3
        assert report.duration_seconds == 120.5
        assert report.source_filter == "gutenberg"

    def test_report_to_dict(self) -> None:
        """Verifica conversao de relatorio para dict."""
        reporter = JobReporter()
        job_id = uuid4()

        report = reporter.create_report(
            job_id=job_id,
            status="completed",
            books_fetched=10,
            books_processed=8,
        )

        d = report.to_dict()

        assert d["job_id"] == str(job_id)
        assert d["status"] == "completed"
        assert d["books_fetched"] == 10
        assert d["books_processed"] == 8
        assert d["failures_by_stage"] == {}

    def test_report_to_json(self) -> None:
        """Verifica conversao de relatorio para JSON."""
        reporter = JobReporter()
        job_id = uuid4()

        report = reporter.create_report(
            job_id=job_id,
            status="completed",
        )

        json_str = report.to_json()

        assert isinstance(json_str, str)
        assert str(job_id) in json_str
        assert "completed" in json_str


class TestJobReporterLogging:
    """Testes de logging de relatorios."""

    def test_log_report(self, caplog: pytest.LogCaptureFixture) -> None:
        """Verifica que relatorio e logado."""
        import logging

        reporter = JobReporter()
        job_id = uuid4()

        report = reporter.create_report(
            job_id=job_id,
            status="completed",
        )

        with caplog.at_level(logging.INFO):
            reporter.log_report(report)

        assert any(str(job_id) in record.message for record in caplog.records)


class TestJobReporterStorage:
    """Testes de armazenamento de relatorios."""

    @pytest.mark.asyncio
    async def test_store_report_with_mongo(self) -> None:
        """Verifica armazenamento com MongoDB configurado."""
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_collection.insert_one = AsyncMock()
        mock_db.get_collection = MagicMock(return_value=mock_collection)

        reporter = JobReporter(mongo_db=mock_db)
        job_id = uuid4()

        report = reporter.create_report(
            job_id=job_id,
            status="completed",
        )

        await reporter.store_report(report)

        mock_collection.insert_one.assert_called_once()
        call_args = mock_collection.insert_one.call_args[0][0]
        assert call_args["job_id"] == str(job_id)
        assert "created_at" in call_args

    @pytest.mark.asyncio
    async def test_store_report_without_mongo(self) -> None:
        """Verifica que sem MongoDB nao ha erro."""
        reporter = JobReporter()  # Sem mongo_db
        job_id = uuid4()

        report = reporter.create_report(
            job_id=job_id,
            status="completed",
        )

        # Nao deve lancar excecao
        await reporter.store_report(report)

    @pytest.mark.asyncio
    async def test_store_report_handles_mongo_error(self) -> None:
        """Verifica que erro do MongoDB e tratado graciosamente."""
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_collection.insert_one = AsyncMock(
            side_effect=RuntimeError("MongoDB unavailable")
        )
        mock_db.get_collection = MagicMock(return_value=mock_collection)

        reporter = JobReporter(mongo_db=mock_db)
        job_id = uuid4()

        report = reporter.create_report(
            job_id=job_id,
            status="completed",
        )

        # Nao deve lancar excecao
        await reporter.store_report(report)
