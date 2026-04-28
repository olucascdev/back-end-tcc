"""
Testes de persistencia de sessao e historico de conversas.

Cobertura:
- get_or_create_session: cria nova e retorna existente
- save_message: persiste mensagens com e sem fontes
- get_conversation_history: recupera historico ordenado
- update_session_memory: atualiza campo memory da sessao
- Mock de repositorios para testes sem banco real
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def project_id() -> str:
    """UUID de projeto para testes."""
    return str(uuid4())


@pytest.fixture
def session_id() -> str:
    """ID de sessao para testes."""
    return "test-session-persist-1"


# ---------------------------------------------------------------------------
# Testes do session_repository
# ---------------------------------------------------------------------------


class TestGetOrCreateSession:
    """Testes da funcao get_or_create_session."""

    @patch("app.infrastructure.database.session_repository.get_db_connection")
    def test_creates_new_session_when_not_exists(
        self, mock_get_conn, project_id, session_id
    ) -> None:
        """Sessao inexistente e criada no banco."""
        from app.infrastructure.database.session_repository import get_or_create_session

        # Mock: SELECT retorna None (sessao nao existe)
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = [
            None,  # SELECT nao encontra
            (session_id, project_id, {}, datetime.now(UTC)),  # INSERT retorna
        ]
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.commit = MagicMock()
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

        result = get_or_create_session(session_id=session_id, project_id=project_id)

        assert result["session_id"] == session_id
        assert result["project_id"] == project_id
        assert result["memory"] == {}
        # Verifica que INSERT foi executado
        assert mock_cursor.execute.call_count == 2

    @patch("app.infrastructure.database.session_repository.get_db_connection")
    def test_returns_existing_session(
        self, mock_get_conn, project_id, session_id
    ) -> None:
        """Sessao existente e retornada sem criar nova."""
        from app.infrastructure.database.session_repository import get_or_create_session

        existing_memory = {"last_topic": "metodologia"}
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (
            session_id,
            project_id,
            existing_memory,
            datetime.now(UTC),
        )
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

        result = get_or_create_session(session_id=session_id, project_id=project_id)

        assert result["session_id"] == session_id
        assert result["memory"] == existing_memory
        # Apenas SELECT executado, sem INSERT
        assert mock_cursor.execute.call_count == 1


class TestUpdateSessionMemory:
    """Testes da funcao update_session_memory."""

    @patch("app.infrastructure.database.session_repository.get_db_connection")
    def test_updates_memory_successfully(self, mock_get_conn, session_id) -> None:
        """Memoria da sessao e atualizada com sucesso."""
        from app.infrastructure.database.session_repository import update_session_memory

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 1
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.commit = MagicMock()
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

        new_memory = {"topics": ["introducao", "metodologia"], "turn_count": 5}
        update_session_memory(session_id=session_id, memory=new_memory)

        # Verifica que UPDATE foi executado
        mock_cursor.execute.assert_called_once()
        mock_conn.commit.assert_called_once()

    @patch("app.infrastructure.database.session_repository.get_db_connection")
    def test_raises_when_session_not_found(self, mock_get_conn, session_id) -> None:
        """Atualizar memoria de sessao inexistente levanta ValueError."""
        from app.infrastructure.database.session_repository import update_session_memory

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 0  # Nenhuma linha afetada
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

        with pytest.raises(ValueError, match="nao encontrada"):
            update_session_memory(session_id=session_id, memory={"key": "value"})


# ---------------------------------------------------------------------------
# Testes do conversation_repository
# ---------------------------------------------------------------------------


class TestSaveMessage:
    """Testes da funcao save_message."""

    @patch("app.infrastructure.database.conversation_repository.get_db_connection")
    def test_saves_user_message(self, mock_get_conn, project_id, session_id) -> None:
        """Mensagem do usuario e salva sem fontes."""
        from app.infrastructure.database.conversation_repository import save_message

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.commit = MagicMock()
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

        save_message(
            session_id=session_id,
            project_id=project_id,
            role="user",
            content="Qual o objetivo do documento?",
        )

        mock_cursor.execute.assert_called_once()
        mock_conn.commit.assert_called_once()

    @patch("app.infrastructure.database.conversation_repository.get_db_connection")
    def test_saves_assistant_message_with_sources(
        self, mock_get_conn, project_id, session_id
    ) -> None:
        """Mensagem do assistant e salva com fontes."""
        from app.infrastructure.database.conversation_repository import save_message

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.commit = MagicMock()
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

        sources = [{"document": "doc-1", "page": 3, "section": "Intro", "score": 0.95}]
        save_message(
            session_id=session_id,
            project_id=project_id,
            role="assistant",
            content="O objetivo e analisar...",
            sources=sources,
        )

        mock_cursor.execute.assert_called_once()
        # Verifica que fontes foram passadas (5o parametro da query)
        params = mock_cursor.execute.call_args[0][1]
        assert params[4] is not None  # sources foi passado
        mock_conn.commit.assert_called_once()

    @patch("app.infrastructure.database.conversation_repository.get_db_connection")
    def test_saves_message_with_empty_sources(
        self, mock_get_conn, project_id, session_id
    ) -> None:
        """Mensagem sem fontes usa lista vazia como default."""
        from app.infrastructure.database.conversation_repository import save_message

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.commit = MagicMock()
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

        save_message(
            session_id=session_id,
            project_id=project_id,
            role="assistant",
            content="Nao encontrei informacoes.",
            sources=None,
        )

        # Verifica que sources=None foi convertido para lista vazia
        params = mock_cursor.execute.call_args[0][1]
        assert params[4] is not None  # sources foi passado como Json([])


class TestGetConversationHistory:
    """Testes da funcao get_conversation_history."""

    @patch("app.infrastructure.database.conversation_repository.get_db_connection")
    def test_returns_history_in_chronological_order(
        self, mock_get_conn, session_id
    ) -> None:
        """Historico retorna em ordem cronologica (mais antigo primeiro)."""
        from app.infrastructure.database.conversation_repository import (
            get_conversation_history,
        )

        now = datetime.now(UTC)
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        # Banco retorna em ordem DESC (mais recente primeiro)
        mock_cursor.fetchall.return_value = [
            ("assistant", "Resposta 2", [], now),
            ("user", "Pergunta 2", [], now),
            ("assistant", "Resposta 1", [], now),
            ("user", "Pergunta 1", [], now),
        ]
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

        history = get_conversation_history(session_id=session_id, limit=10)

        assert len(history) == 4
        # Ordem cronologica: mais antigo primeiro
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "Pergunta 1"
        assert history[1]["role"] == "assistant"
        assert history[1]["content"] == "Resposta 1"
        assert history[2]["content"] == "Pergunta 2"
        assert history[3]["content"] == "Resposta 2"

    @patch("app.infrastructure.database.conversation_repository.get_db_connection")
    def test_respects_limit_parameter(self, mock_get_conn, session_id) -> None:
        """Parametro limit restringe numero de mensagens retornadas."""
        from app.infrastructure.database.conversation_repository import (
            get_conversation_history,
        )

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ("assistant", "Ultima resposta", [], datetime.now(UTC)),
        ]
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

        history = get_conversation_history(session_id=session_id, limit=1)

        assert len(history) == 1
        # Verifica que LIMIT=1 foi passado na query (2o parametro)
        params = mock_cursor.execute.call_args[0][1]
        assert params[1] == 1

    @patch("app.infrastructure.database.conversation_repository.get_db_connection")
    def test_returns_empty_list_for_new_session(
        self, mock_get_conn, session_id
    ) -> None:
        """Sessao sem conversas retorna lista vazia."""
        from app.infrastructure.database.conversation_repository import (
            get_conversation_history,
        )

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

        history = get_conversation_history(session_id=session_id)

        assert history == []

    @patch("app.infrastructure.database.conversation_repository.get_db_connection")
    def test_history_includes_sources(self, mock_get_conn, session_id) -> None:
        """Historico inclui fontes quando presentes."""
        from app.infrastructure.database.conversation_repository import (
            get_conversation_history,
        )

        sources_data = [
            {"document": "doc-1", "page": 5, "section": "Results", "score": 0.92}
        ]
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ("assistant", "Resposta com fontes", sources_data, datetime.now(UTC)),
        ]
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

        history = get_conversation_history(session_id=session_id)

        assert len(history) == 1
        assert history[0]["sources"] == sources_data
        assert history[0]["role"] == "assistant"
