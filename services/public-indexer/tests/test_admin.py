"""
Testes dos endpoints administrativos.

Verifica POST /admin/index/run e GET /admin/index/jobs/{job_id}
com dependencias mockadas.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.v1.endpoints import admin as admin_endpoints
from app.domain.models import IndexerJob, JobStatus
from app.main import create_app


@pytest.fixture
def mock_clients():
    """Mock de todos os clientes de infraestrutura."""
    pg = MagicMock()
    pg.check_health.return_value = True

    mongo = MagicMock()
    mongo.check_health = AsyncMock(return_value=True)

    minio = MagicMock()
    minio.check_health.return_value = True

    redis = MagicMock()
    redis.check_health = AsyncMock(return_value=True)

    return {"pg": pg, "mongo": mongo, "minio": minio, "redis": redis}


@pytest.fixture
def mock_usecases():
    """Mock dos casos de uso."""
    from app.application.usecases import GetJobStatusUseCase, RunIndexUseCase

    run_uc = AsyncMock(spec=RunIndexUseCase)
    get_uc = MagicMock(spec=GetJobStatusUseCase)
    return {"run": run_uc, "get": get_uc}


@pytest.fixture
def client(mock_clients, mock_usecases):
    """Cliente de teste com app configurado e dependencias mockadas."""
    app = create_app()

    # Injeta clientes mockados no app state
    app.state.pg_client = mock_clients["pg"]
    app.state.mongo_client = mock_clients["mongo"]
    app.state.minio_client = mock_clients["minio"]
    app.state.redis_client = mock_clients["redis"]

    # Override das dependencias admin
    async def _provide_run_uc():
        return mock_usecases["run"]

    async def _provide_get_uc():
        return mock_usecases["get"]

    app.dependency_overrides[admin_endpoints._get_run_index_usecase] = _provide_run_uc
    app.dependency_overrides[admin_endpoints._get_get_job_usecase] = _provide_get_uc

    yield TestClient(app)

    # Limpa overrides
    app.dependency_overrides.clear()


class TestRunIndexEndpoint:
    """Testes de POST /api/v1/admin/index/run."""

    def test_run_index_returns_job_id(self, client: TestClient, mock_usecases) -> None:
        """Verifica que endpoint retorna job_id e status."""
        job_id = uuid4()
        mock_job = IndexerJob(job_id=job_id, status=JobStatus.PENDING, dry_run=False)
        mock_usecases["run"].execute.return_value = mock_job

        res = client.post("/api/v1/admin/index/run", json={})
        assert res.status_code == 200
        data = res.json()
        assert data["job_id"] == str(job_id)
        assert data["status"] == "pending"
        assert data["dry_run"] is False

    def test_run_index_with_dry_run(self, client: TestClient, mock_usecases) -> None:
        """Verifica que dry_run e repassado ao caso de uso."""
        job_id = uuid4()
        mock_job = IndexerJob(job_id=job_id, status=JobStatus.COMPLETED, dry_run=True)
        mock_usecases["run"].execute.return_value = mock_job

        res = client.post("/api/v1/admin/index/run", json={"dry_run": True})
        assert res.status_code == 200
        data = res.json()
        assert data["dry_run"] is True

    def test_run_index_with_source_filter(
        self, client: TestClient, mock_usecases
    ) -> None:
        """Verifica que source_filter e repassado ao caso de uso."""
        job_id = uuid4()
        mock_job = IndexerJob(
            job_id=job_id,
            status=JobStatus.PENDING,
            source_filter="gutenberg",
        )
        mock_usecases["run"].execute.return_value = mock_job

        res = client.post(
            "/api/v1/admin/index/run",
            json={"source_filter": "gutenberg"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["job_id"] == str(job_id)


class TestGetJobStatusEndpoint:
    """Testes de GET /api/v1/admin/index/jobs/{job_id}."""

    def test_get_job_returns_status(self, client: TestClient, mock_usecases) -> None:
        """Verifica que endpoint retorna status do job."""
        job_id = uuid4()
        mock_job = IndexerJob(
            job_id=job_id,
            status=JobStatus.RUNNING,
            source_filter="openlibrary",
        )
        mock_usecases["get"].execute.return_value = mock_job

        res = client.get(f"/api/v1/admin/index/jobs/{job_id}")
        assert res.status_code == 200
        data = res.json()
        assert data["job_id"] == str(job_id)
        assert data["status"] == "running"
        assert data["source_filter"] == "openlibrary"
        assert "created_at" in data

    def test_get_job_not_found(self, client: TestClient, mock_usecases) -> None:
        """Verifica que retorna 404 para job inexistente."""
        mock_usecases["get"].execute.return_value = None

        res = client.get(f"/api/v1/admin/index/jobs/{uuid4()}")
        assert res.status_code == 404
        data = res.json()
        assert "detail" in data

    def test_get_job_completed(self, client: TestClient, mock_usecases) -> None:
        """Verifica job completado com timestamps."""
        job_id = uuid4()
        mock_job = IndexerJob(
            job_id=job_id,
            status=JobStatus.COMPLETED,
            items_processed=42,
        )
        mock_job.mark_running()
        mock_job.mark_completed(items_processed=42)
        mock_usecases["get"].execute.return_value = mock_job

        res = client.get(f"/api/v1/admin/index/jobs/{job_id}")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "completed"
        assert data["items_processed"] == 42
        assert data["started_at"] is not None
        assert data["completed_at"] is not None

    def test_get_job_failed(self, client: TestClient, mock_usecases) -> None:
        """Verifica job falhado com mensagem de erro."""
        job_id = uuid4()
        mock_job = IndexerJob(job_id=job_id, status=JobStatus.PENDING)
        mock_job.mark_failed("Connection timeout")
        mock_usecases["get"].execute.return_value = mock_job

        res = client.get(f"/api/v1/admin/index/jobs/{job_id}")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "failed"
        assert data["error_message"] == "Connection timeout"
