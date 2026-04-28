"""
Engine de conexao com PostgreSQL para operacoes sync.

Fornece connection pool e funcao utilitaria para obter conexao.
Usado para atualizar status de documentos no NeonDB.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Generator

import psycopg2
from psycopg2.pool import ThreadedConnectionPool

from app.core.config import Settings

logger = logging.getLogger(__name__)

# Pool global reutilizavel
_pool: ThreadedConnectionPool | None = None


def _get_pool(settings: Settings | None = None) -> ThreadedConnectionPool:
    """Retorna ou cria connection pool singleton."""
    global _pool
    if _pool is None:
        settings = settings or Settings()
        _pool = ThreadedConnectionPool(
            minconn=1,
            maxconn=5,
            dsn=settings.DATABASE_URL,
        )
    return _pool


@contextmanager
def get_db_connection(settings: Settings | None = None) -> Generator:
    """Context manager para obter conexao do pool.

    Uso:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")

    Yields:
        Conexao psycopg2.
    """
    pool = _get_pool(settings)
    conn = pool.getconn()
    try:
        yield conn
    finally:
        pool.putconn(conn)


def update_document_status(
    document_id: str,
    status: str,
    chunks_count: int | None = None,
    error_message: str | None = None,
    settings: Settings | None = None,
) -> None:
    """Atualiza status do documento na tabela documents do NeonDB.

    Args:
        document_id: UUID do documento.
        status: novo status (processing, ready, error).
        chunks_count: numero de chunks gerados (quando ready).
        error_message: mensagem de erro (quando error).
        settings: configuracoes opcionais.
    """
    update_sql = """
        UPDATE documents
        SET status = %s,
            updated_at = NOW()
            {chunks_clause}
            {error_clause}
        WHERE id = %s
    """

    chunks_clause = ", chunks_count = %s" if chunks_count is not None else ""
    error_clause = ", error_message = %s" if error_message is not None else ""

    sql = update_sql.format(chunks_clause=chunks_clause, error_clause=error_clause)

    params: list = [status]
    if chunks_count is not None:
        params.append(chunks_count)
    if error_message is not None:
        params.append(error_message)
    params.append(document_id)

    with get_db_connection(settings) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
        conn.commit()

    logger.info("Documento %s atualizado: status=%s", document_id, status)


def close_pool() -> None:
    """Fecha o connection pool global."""
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None
        logger.info("Connection pool database fechado")
