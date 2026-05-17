"""
Clientes de infraestrutura para o public-indexer.

Gerencia conexoes com MongoDB, PostgreSQL, MinIO e Redis.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from psycopg_pool import ConnectionPool
from minio import Minio
from motor.motor_asyncio import AsyncIOMotorClient
from redis.asyncio import Redis

from app.core.config import Settings

logger = logging.getLogger(__name__)


class PostgresClient:
    """Cliente PostgreSQL com pool de conexoes sync (psycopg3)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._pool: ConnectionPool | None = None

    async def connect(self) -> None:
        """Abre pool de conexoes PostgreSQL."""
        # psycopg3 ConnectionPool e sync, mas criamos no startup
        self._pool = ConnectionPool(
            conninfo=self._settings.DB_URL,
            min_size=2,
            max_size=10,
        )
        logger.info("PostgreSQL pool conectado")

    async def close(self) -> None:
        """Fecha pool de conexoes PostgreSQL."""
        if self._pool is not None:
            self._pool.close()
            self._pool = None
            logger.info("PostgreSQL pool fechado")

    @asynccontextmanager
    async def get_connection(self):
        """Context manager para obter conexao do pool."""
        if self._pool is None:
            raise RuntimeError("PostgreSQL pool nao inicializado")
        with self._pool.connection() as conn:
            yield conn

    def check_health(self) -> bool:
        """Verifica conectividade PostgreSQL."""
        try:
            if self._pool is None:
                return False
            with self._pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    return True
        except Exception:
            return False


class MongoDBClient:
    """Cliente MongoDB assincrono (motor)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: AsyncIOMotorClient | None = None

    async def connect(self) -> None:
        """Abre conexao MongoDB."""
        self._client = AsyncIOMotorClient(self._settings.MONGO_URL)
        # Ping para validar conexao
        await self._client.admin.command("ping")
        logger.info("MongoDB conectado")

    async def close(self) -> None:
        """Fecha conexao MongoDB."""
        if self._client is not None:
            self._client.close()
            self._client = None
            logger.info("MongoDB fechado")

    @property
    def db(self):
        """Retorna referencia ao database configurado."""
        if self._client is None:
            raise RuntimeError("MongoDB nao inicializado")
        return self._client[self._settings.MONGO_DB]

    async def check_health(self) -> bool:
        """Verifica conectividade MongoDB."""
        try:
            if self._client is None:
                return False
            await self._client.admin.command("ping")
            return True
        except Exception:
            return False


class MinIOClient:
    """Cliente MinIO/S3 para armazenamento de artefatos."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: Minio | None = None

    def connect(self) -> None:
        """Inicializa cliente MinIO."""
        self._client = Minio(
            endpoint=self._settings.MINIO_ENDPOINT,
            access_key=self._settings.MINIO_ACCESS_KEY,
            secret_key=self._settings.MINIO_SECRET_KEY,
            secure=self._settings.MINIO_USE_SSL,
        )
        # Garante que bucket existe
        if not self._client.bucket_exists(self._settings.MINIO_BUCKET):
            self._client.make_bucket(self._settings.MINIO_BUCKET)
        logger.info("MinIO conectado, bucket '%s' pronto", self._settings.MINIO_BUCKET)

    def close(self) -> None:
        """Libera recursos MinIO (cliente e stateless)."""
        self._client = None
        logger.info("MinIO cliente liberado")

    @property
    def client(self) -> Minio:
        """Retorna instancia MinIO."""
        if self._client is None:
            raise RuntimeError("MinIO nao inicializado")
        return self._client

    def check_health(self) -> bool:
        """Verifica conectividade MinIO."""
        try:
            if self._client is None:
                return False
            return self._client.bucket_exists(self._settings.MINIO_BUCKET)
        except Exception:
            return False


class RedisClient:
    """Cliente Redis assincrono para cache e fila."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: Redis | None = None

    async def connect(self) -> None:
        """Abre conexao Redis."""
        self._client = Redis.from_url(
            self._settings.REDIS_URL,
            decode_responses=True,
        )
        await self._client.ping()
        logger.info("Redis conectado")

    async def close(self) -> None:
        """Fecha conexao Redis."""
        if self._client is not None:
            await self._client.close()
            self._client = None
            logger.info("Redis fechado")

    @property
    def client(self) -> Redis:
        """Retorna instancia Redis."""
        if self._client is None:
            raise RuntimeError("Redis nao inicializado")
        return self._client

    async def check_health(self) -> bool:
        """Verifica conectividade Redis."""
        try:
            if self._client is None:
                return False
            return await self._client.ping()
        except Exception:
            return False
