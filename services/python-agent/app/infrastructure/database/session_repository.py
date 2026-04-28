"""
Repositorio de sessoes de agente.

Responsavel por persistir e recuperar sessoes de chat no NeonDB
(tabela agent_sessions). Usa psycopg2 para operacoes SQL sync.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

import psycopg2
from psycopg2.extras import Json

from app.core.config import Settings
from app.core.database import get_db_connection

logger = logging.getLogger(__name__)


def get_or_create_session(
    session_id: str,
    project_id: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Retorna sessao existente ou cria nova no banco.

    Args:
        session_id: identificador unico da sessao.
        project_id: UUID do projeto vinculado.
        settings: configuracoes opcionais de banco.

    Returns:
        Dict com chaves: session_id, project_id, memory, created_at.
    """
    select_sql = """
        SELECT session_id, project_id::text, memory, created_at
        FROM agent_sessions
        WHERE session_id = %s
    """

    insert_sql = """
        INSERT INTO agent_sessions (session_id, project_id, memory)
        VALUES (%s, %s, %s)
        RETURNING session_id, project_id::text, memory, created_at
    """

    with get_db_connection(settings) as conn:
        with conn.cursor() as cur:
            # Tenta buscar sessao existente
            cur.execute(select_sql, (session_id,))
            row = cur.fetchone()

            if row is not None:
                logger.debug("Sessao encontrada: session_id=%s", session_id)
                return {
                    "session_id": row[0],
                    "project_id": row[1],
                    "memory": row[2] if isinstance(row[2], dict) else {},
                    "created_at": row[3],
                }

            # Sessao nao existe — cria nova
            cur.execute(insert_sql, (session_id, project_id, Json({})))
            row = cur.fetchone()
            conn.commit()

            logger.info(
                "Nova sessao criada: session_id=%s, project_id=%s",
                session_id,
                project_id,
            )
            return {
                "session_id": row[0],
                "project_id": row[1],
                "memory": row[2] if isinstance(row[2], dict) else {},
                "created_at": row[3],
            }


def update_session_memory(
    session_id: str,
    memory: dict[str, Any],
    settings: Settings | None = None,
) -> None:
    """Atualiza campo memory de uma sessao existente.

    Args:
        session_id: identificador da sessao.
        memory: dict com dados de memoria a persistir.
        settings: configuracoes opcionais de banco.

    Raises:
        psycopg2.Error: se sessao nao existir ou falha de conexao.
    """
    update_sql = """
        UPDATE agent_sessions
        SET memory = %s, updated_at = NOW()
        WHERE session_id = %s
    """

    with get_db_connection(settings) as conn:
        with conn.cursor() as cur:
            cur.execute(update_sql, (Json(memory), session_id))
            if cur.rowcount == 0:
                logger.warning(
                    "Sessao nao encontrada para atualizar memoria: %s", session_id
                )
                raise ValueError(f"Sessao '{session_id}' nao encontrada")
        conn.commit()

    logger.debug("Memoria atualizada para sessao: session_id=%s", session_id)
