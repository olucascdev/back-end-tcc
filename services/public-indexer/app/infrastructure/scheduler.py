"""
Scheduler assincrono para execucao periodica de indexacao.

Usa lock distribuido via Redis para prevenir execucoes sobrepostas
e integra com o pipeline completo de sincronizacao e indexacao.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Optional

from redis.asyncio import Redis

from app.application.catalog_sync import CatalogSyncUseCase
from app.application.usecases import RunIndexUseCase

logger = logging.getLogger(__name__)

LOCK_KEY = "public-indexer:scheduler:lock"


class IndexScheduler:
    """
    Agenda execucoes periodicas do pipeline de indexacao.

    Usa lock distribuido Redis para garantir que apenas uma
    instancia execute por vez em ambiente multi-replica.
    """

    def __init__(
        self,
        redis_client: Redis,
        catalog_sync: CatalogSyncUseCase,
        run_index: RunIndexUseCase,
        sync_interval_minutes: int = 60,
    ) -> None:
        """
        Inicializa scheduler.

        Args:
            redis_client: cliente Redis para lock distribuido.
            catalog_sync: caso de uso de sincronizacao de catalogo.
            run_index: caso de uso de indexacao.
            sync_interval_minutes: intervalo entre execucoes em minutos.
        """
        self._redis = redis_client
        self._catalog_sync = catalog_sync
        self._run_index = run_index
        self._interval_seconds = sync_interval_minutes * 60
        self._lock_ttl = sync_interval_minutes * 2 * 60  # TTL = 2x intervalo
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._lock_value: Optional[str] = None

    async def start(self) -> None:
        """Inicia scheduler como background task."""
        if self._running:
            logger.warning("Scheduler ja esta em execucao")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "Scheduler iniciado: intervalo=%d min",
            self._interval_seconds // 60,
        )

    async def stop(self) -> None:
        """Para scheduler gracefulmente."""
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        # Libera lock se ainda estiver ativo
        if self._lock_value:
            await self._release_lock()

        logger.info("Scheduler parado")

    async def _run_loop(self) -> None:
        """Loop principal do scheduler."""
        # Primeira execucao apos o intervalo
        await asyncio.sleep(self._interval_seconds)

        while self._running:
            try:
                acquired = await self._acquire_lock()
                if not acquired:
                    logger.info("Lock nao adquirido, outra instancia executando. Skip.")
                    await asyncio.sleep(self._interval_seconds)
                    continue

                await self._execute_pipeline()

            except asyncio.CancelledError:
                logger.info("Scheduler cancelado")
                break
            except Exception as exc:
                logger.error("Erro no scheduler: %s", exc)

            # Aguarda proximo intervalo
            if self._running:
                await asyncio.sleep(self._interval_seconds)

    async def _acquire_lock(self) -> bool:
        """
        Tenta adquirir lock distribuido via Redis.

        Returns:
            True se lock adquirido com sucesso.
        """
        self._lock_value = str(uuid.uuid4())
        try:
            acquired = await self._redis.set(
                LOCK_KEY,
                self._lock_value,
                nx=True,  # Apenas se nao existir
                ex=self._lock_ttl,
            )
            if acquired:
                logger.info("Lock adquirido: value=%s", self._lock_value[:8])
            return bool(acquired)
        except Exception as exc:
            logger.error("Falha ao adquirir lock: %s", exc)
            return False

    async def _release_lock(self) -> None:
        """Libera lock distribuido se ainda for o owner."""
        if not self._lock_value:
            return

        try:
            # Verifica se ainda somos o owner antes de liberar
            current_value = await self._redis.get(LOCK_KEY)
            if current_value == self._lock_value:
                await self._redis.delete(LOCK_KEY)
                logger.info("Lock liberado: value=%s", self._lock_value[:8])
        except Exception as exc:
            logger.warning("Falha ao liberar lock: %s", exc)
        finally:
            self._lock_value = None

    async def _execute_pipeline(self) -> None:
        """Executa pipeline completo: sync + index."""
        job_id = str(uuid.uuid4())
        logger.info("Iniciando pipeline agendado: job_id=%s", job_id)

        try:
            # Fase 1: Sincroniza catalogo
            logger.info("Fase 1: Sincronizacao de catalogo")
            sync_reports = await self._catalog_sync.execute()

            total_new = sum(r.new for r in sync_reports.values())
            total_updated = sum(r.updated for r in sync_reports.values())
            logger.info(
                "Catalogo sincronizado: new=%d, updated=%d",
                total_new,
                total_updated,
            )

            # Fase 2: Executa indexacao
            logger.info("Fase 2: Indexacao de livros pendentes")
            job = await self._run_index.execute()

            logger.info(
                "Pipeline concluido: job_id=%s, processed=%d",
                job_id,
                job.items_processed,
            )

        except Exception as exc:
            logger.error("Pipeline falhou: job_id=%s, error=%s", job_id, exc)
        finally:
            await self._release_lock()

    @property
    def is_running(self) -> bool:
        """Retorna True se scheduler esta ativo."""
        return self._running
