"""
Armazenamento e busca de embeddings no PostgreSQL com extensao pgvector.

Operacoes sync via psycopg2 para compatibilidade com fluxo de processamento.
"""

from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from typing import Any

import psycopg2
from psycopg2.extras import Json, execute_values
from psycopg2.pool import ThreadedConnectionPool

from app.core.config import Settings

logger = logging.getLogger(__name__)


class PgVectorStore:
    """Operacoes de insercao e busca de embeddings no pgvector."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or Settings()
        self._pool: ThreadedConnectionPool | None = None

    def _get_pool(self) -> ThreadedConnectionPool:
        """Retorna ou cria connection pool."""
        if self._pool is None:
            self._pool = ThreadedConnectionPool(
                minconn=1,
                maxconn=5,
                dsn=self._settings.DATABASE_URL,
            )
        return self._pool

    @contextmanager
    def _get_connection(self):
        """Context manager para conexao do pool."""
        pool = self._get_pool()
        conn = pool.getconn()
        try:
            yield conn
        finally:
            pool.putconn(conn)

    def insert_embeddings(self, embeddings_data: list[dict]) -> int:
        """Insere embeddings no banco com operacao bulk.

        Args:
            embeddings_data: lista de dicts com chaves:
                - content: texto do chunk
                - embedding: list[float] do embedding
                - metadata: dict com project_id, document_id, page_number, chunk_index

        Returns:
            Numero de registros inseridos.
        """
        if not embeddings_data:
            return 0

        insert_sql = """
            INSERT INTO document_embeddings (content, embedding, metadata)
            VALUES %s
        """

        values = [
            (
                item["content"],
                item["embedding"],
                Json(item.get("metadata", {})),
            )
            for item in embeddings_data
        ]

        with self._get_connection() as conn:
            with conn.cursor() as cur:
                execute_values(cur, insert_sql, values, page_size=100)
            conn.commit()

        logger.info("Inseridos %d embeddings no pgvector", len(values))
        return len(values)

    def search_similar(
        self,
        project_id: str,
        query_embedding: list[float],
        top_k: int = 5,
    ) -> list[dict]:
        """Busca chunks similares por distancia cosseno no pgvector.

        Usa operador <-> (distancia L2) do pgvector.

        Args:
            project_id: filtro por projeto.
            query_embedding: vetor de consulta.
            top_k: numero de resultados.

        Returns:
            Lista de dicts com content, metadata e similarity score.
        """
        search_sql = """
            SELECT
                content,
                metadata,
                embedding <-> %s::vector AS distance
            FROM document_embeddings
            WHERE metadata->>'project_id' = %s
            ORDER BY distance ASC
            LIMIT %s
        """

        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(search_sql, (query_embedding, project_id, top_k))
                rows = cur.fetchall()

        results = []
        for content, metadata, distance in rows:
            results.append(
                {
                    "content": content,
                    "metadata": metadata if isinstance(metadata, dict) else {},
                    "score": 1.0 - distance,  # converte distancia para similaridade
                }
            )

        logger.debug(
            "Busca similar: %d resultados para project_id=%s", len(results), project_id
        )
        return results

    def search_similar_by_project(
        self,
        project_id: str,
        query_embedding: list[float],
        top_k: int = 5,
        min_score: float = 0.7,
    ) -> list[dict]:
        """Busca chunks similares filtrando por project_id com score minimo.

        Usa operador <-> (distancia L2) do pgvector e converte para
        similaridade cosseno (1 - distance).

        Args:
            project_id: filtro por projeto no metadata JSONB.
            query_embedding: vetor de consulta gerado pelo embedder.
            top_k: numero maximo de resultados.
            min_score: similaridade minima para incluir resultado (0-1).

        Returns:
            Lista de dicts com content, metadata e similarity score,
            ordenados por score descendente e filtrados por min_score.
        """
        search_sql = """
            SELECT
                content,
                metadata,
                embedding <-> %s::vector AS distance
            FROM document_embeddings
            WHERE metadata->>'project_id' = %s
            ORDER BY distance ASC
            LIMIT %s
        """

        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(search_sql, (query_embedding, project_id, top_k))
                rows = cur.fetchall()

        results = []
        for content, metadata, distance in rows:
            score = 1.0 - distance
            if score >= min_score:
                results.append(
                    {
                        "content": content,
                        "metadata": metadata if isinstance(metadata, dict) else {},
                        "score": score,
                    }
                )

        logger.debug(
            "Busca por projeto: %d resultados (min_score=%.2f) para project_id=%s",
            len(results),
            min_score,
            project_id,
        )
        return results

    def close(self) -> None:
        """Fecha o connection pool."""
        if self._pool is not None:
            self._pool.closeall()
            self._pool = None
            logger.info("Connection pool pgvector fechado")
