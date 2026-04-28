"""
Repositorio de conversas.

Responsavel por persistir e recuperar mensagens de chat no NeonDB
(tabela conversations). Usa psycopg2 para operacoes SQL sync.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from psycopg2.extras import Json

from app.core.config import Settings
from app.core.database import get_db_connection

logger = logging.getLogger(__name__)


def save_message(
    session_id: str,
    project_id: str,
    role: str,
    content: str,
    sources: list[dict[str, Any]] | None = None,
    settings: Settings | None = None,
) -> None:
    """Salva uma mensagem de conversa no banco.

    Args:
        session_id: identificador da sessao de chat.
        project_id: UUID do projeto vinculado.
        role: 'user' ou 'assistant'.
        content: texto da mensagem.
        sources: lista de fontes (apenas para role='assistant').
        settings: configuracoes opcionais de banco.
    """
    insert_sql = """
        INSERT INTO conversations (project_id, session_id, role, content, sources)
        VALUES (%s, %s, %s, %s, %s)
    """

    sources_json = Json(sources or [])

    with get_db_connection(settings) as conn:
        with conn.cursor() as cur:
            cur.execute(
                insert_sql, (project_id, session_id, role, content, sources_json)
            )
        conn.commit()

    logger.debug(
        "Mensagem salva: session_id=%s, role=%s, content_len=%d",
        session_id,
        role,
        len(content),
    )


def get_conversation_history(
    session_id: str,
    limit: int = 10,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Retorna historico de conversas de uma sessao.

    Args:
        session_id: identificador da sessao.
        limit: numero maximo de mensagens (mais recentes).
        settings: configuracoes opcionais de banco.

    Returns:
        Lista de dicts com role, content, sources, created_at.
    """
    select_sql = """
        SELECT role, content, sources, created_at
        FROM conversations
        WHERE session_id = %s
        ORDER BY created_at DESC
        LIMIT %s
    """

    with get_db_connection(settings) as conn:
        with conn.cursor() as cur:
            cur.execute(select_sql, (session_id, limit))
            rows = cur.fetchall()

    # Inverte para ordem cronologica (mais antigo primeiro)
    history = []
    for role, content, sources, created_at in reversed(rows):
        history.append(
            {
                "role": role,
                "content": content,
                "sources": sources if isinstance(sources, list) else [],
                "created_at": created_at,
            }
        )

    logger.debug(
        "Historico recuperado: session_id=%s, %d mensagens",
        session_id,
        len(history),
    )
    return history
