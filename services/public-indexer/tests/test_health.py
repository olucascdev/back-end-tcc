"""
Testes do endpoint de health check.

Verifica GET /health e GET /health/ready com dependencias mockadas.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.v1.endpoints import admin as admin_endpoints
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


class TestHealthEndpoint:
    """Testes de GET /api/v1/health."""

    def test_health_returns_ok(self, client: TestClient) -> None:
        """Verifica que health retorna 200 com status ok."""
        res = client.get("/api/v1/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert data["service"] == "public-indexer"


class TestReadinessEndpoint:
    """Testes de GET /api/v1/health/ready."""

    def test_ready_all_ok(self, client: TestClient) -> None:
        """Verifica readiness com todas as dependencias saudaveis."""
        res = client.get("/api/v1/health/ready")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ready"
        assert data["checks"]["postgresql"] == "ok"
        assert data["checks"]["mongodb"] == "ok"
        assert data["checks"]["minio"] == "ok"
        assert data["checks"]["redis"] == "ok"

    def test_ready_postgres_fails(self, client: TestClient) -> None:
        """Verifica readiness quando PostgreSQL falha."""
        client.app.state.pg_client.check_health.return_value = False

        res = client.get("/api/v1/health/ready")
        assert res.status_code == 503
        data = res.json()
        assert data["status"] == "degraded"
        assert data["checks"]["postgresql"] == "error"

    def test_ready_mongo_fails(self, client: TestClient) -> None:
        """Verifica readiness quando MongoDB falha."""
        client.app.state.mongo_client.check_health = AsyncMock(return_value=False)

        res = client.get("/api/v1/health/ready")
        assert res.status_code == 503
        data = res.json()
        assert data["status"] == "degraded"
        assert data["checks"]["mongodb"] == "error"

    def test_ready_minio_fails(self, client: TestClient) -> None:
        """Verifica readiness quando MinIO falha."""
        client.app.state.minio_client.check_health.return_value = False

        res = client.get("/api/v1/health/ready")
        assert res.status_code == 503
        data = res.json()
        assert data["status"] == "degraded"
        assert data["checks"]["minio"] == "error"

    def test_ready_redis_fails(self, client: TestClient) -> None:
        """Verifica readiness quando Redis falha."""
        client.app.state.redis_client.check_health = AsyncMock(return_value=False)

        res = client.get("/api/v1/health/ready")
        assert res.status_code == 503
        data = res.json()
        assert data["status"] == "degraded"
        assert data["checks"]["redis"] == "error"
