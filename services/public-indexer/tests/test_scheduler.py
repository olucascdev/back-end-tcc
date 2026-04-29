"""
Testes do IndexScheduler.

Verifica lock distribuido, execucao periodica e shutdown graceful.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.infrastructure.scheduler import IndexScheduler, LOCK_KEY


@pytest.fixture
def mock_redis() -> MagicMock:
    """Mock do cliente Redis."""
    redis = MagicMock()
    redis.set = AsyncMock(return_value=True)
    redis.get = AsyncMock(return_value=None)
    redis.delete = AsyncMock(return_value=1)
    return redis


@pytest.fixture
def mock_catalog_sync() -> MagicMock:
    """Mock do caso de uso de sync."""
    from app.application.catalog_sync import SyncReport

    sync = MagicMock()
    sync.execute = AsyncMock(
        return_value={
            "gutenberg": SyncReport(new=2, updated=0, unchanged=0, errors=0),
        }
    )
    return sync


@pytest.fixture
def mock_run_index() -> MagicMock:
    """Mock do caso de uso de index."""
    from app.domain.models import IndexerJob

    run = MagicMock()
    job = IndexerJob()
    job.mark_completed(items_processed=2)
    run.execute = AsyncMock(return_value=job)
    return run


@pytest.fixture
def scheduler(
    mock_redis: MagicMock,
    mock_catalog_sync: MagicMock,
    mock_run_index: MagicMock,
) -> IndexScheduler:
    """Scheduler com mocks injetados."""
    return IndexScheduler(
        redis_client=mock_redis,
        catalog_sync=mock_catalog_sync,
        run_index=mock_run_index,
        sync_interval_minutes=1,  # 1 minuto para testes rapidos
    )


class TestSchedulerLock:
    """Testes de lock distribuido."""

    @pytest.mark.asyncio
    async def test_acquire_lock_success(
        self, scheduler: IndexScheduler, mock_redis: MagicMock
    ) -> None:
        """Verifica aquisicao de lock com sucesso."""
        mock_redis.set = AsyncMock(return_value=True)

        result = await scheduler._acquire_lock()

        assert result is True
        mock_redis.set.assert_called_once()
        assert scheduler._lock_value is not None

    @pytest.mark.asyncio
    async def test_acquire_lock_failure(
        self, scheduler: IndexScheduler, mock_redis: MagicMock
    ) -> None:
        """Verifica falha na aquisicao de lock (ja持有)."""
        mock_redis.set = AsyncMock(return_value=False)

        result = await scheduler._acquire_lock()

        assert result is False

    @pytest.mark.asyncio
    async def test_release_lock(
        self, scheduler: IndexScheduler, mock_redis: MagicMock
    ) -> None:
        """Verifica liberacao de lock."""
        # Primeiro adquire
        mock_redis.set = AsyncMock(return_value=True)
        await scheduler._acquire_lock()

        # Configura get para retornar o valor do lock
        lock_value = scheduler._lock_value
        mock_redis.get = AsyncMock(return_value=lock_value)

        # Libera
        await scheduler._release_lock()

        mock_redis.delete.assert_called_once_with(LOCK_KEY)
        assert scheduler._lock_value is None

    @pytest.mark.asyncio
    async def test_release_lock_not_owner(
        self, scheduler: IndexScheduler, mock_redis: MagicMock
    ) -> None:
        """Verifica que nao libera lock de outra instancia."""
        mock_redis.set = AsyncMock(return_value=True)
        await scheduler._acquire_lock()

        # Outra instancia持有 o lock
        mock_redis.get = AsyncMock(return_value="other-instance-uuid")

        await scheduler._release_lock()

        # Nao deve chamar delete
        mock_redis.delete.assert_not_called()


class TestSchedulerPipeline:
    """Testes de execucao do pipeline."""

    @pytest.mark.asyncio
    async def test_execute_pipeline(
        self,
        scheduler: IndexScheduler,
        mock_catalog_sync: MagicMock,
        mock_run_index: MagicMock,
    ) -> None:
        """Verifica execucao completa do pipeline."""
        await scheduler._execute_pipeline()

        mock_catalog_sync.execute.assert_called_once()
        mock_run_index.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_pipeline_handles_error(
        self,
        scheduler: IndexScheduler,
        mock_catalog_sync: MagicMock,
    ) -> None:
        """Verifica que erro no pipeline e tratado."""
        mock_catalog_sync.execute = AsyncMock(side_effect=RuntimeError("Sync failed"))

        # Nao deve lancar excecao
        await scheduler._execute_pipeline()


class TestSchedulerLifecycle:
    """Testes de ciclo de vida do scheduler."""

    @pytest.mark.asyncio
    async def test_start_scheduler(self, scheduler: IndexScheduler) -> None:
        """Verifica inicio do scheduler."""
        assert scheduler.is_running is False

        await scheduler.start()

        assert scheduler.is_running is True
        assert scheduler._task is not None

        # Limpa
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_stop_scheduler(self, scheduler: IndexScheduler) -> None:
        """Verifica parada do scheduler."""
        await scheduler.start()
        assert scheduler.is_running is True

        await scheduler.stop()

        assert scheduler.is_running is False

    @pytest.mark.asyncio
    async def test_start_already_running(self, scheduler: IndexScheduler) -> None:
        """Verifica que start duplicado e ignorado."""
        await scheduler.start()
        task1 = scheduler._task

        await scheduler.start()
        task2 = scheduler._task

        # Deve ser a mesma task
        assert task1 is task2

        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_scheduler_skips_when_lock_not_acquired(
        self,
        mock_redis: MagicMock,
        mock_catalog_sync: MagicMock,
        mock_run_index: MagicMock,
    ) -> None:
        """Verifica que scheduler skipa quando lock nao e adquirido."""
        scheduler = IndexScheduler(
            redis_client=mock_redis,
            catalog_sync=mock_catalog_sync,
            run_index=mock_run_index,
            sync_interval_minutes=1,
        )

        # Lock sempre falha
        mock_redis.set = AsyncMock(return_value=False)

        await scheduler.start()

        # Aguarda um pouco para o loop executar
        await asyncio.sleep(0.1)

        await scheduler.stop()

        # Pipeline nao deve ter sido executado
        mock_catalog_sync.execute.assert_not_called()
