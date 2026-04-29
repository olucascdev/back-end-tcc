"""
Testes de integracao com banco de dados real.

Executa operacoes CRUD dos repositorios e PgVectorStore contra
um PostgreSQL real. Pula automaticamente se o banco nao estiver
disponivel (pytest skipif).

Requisitos:
- PostgreSQL com extensao pgvector ativo
- DATABASE_URL configurado apontando para banco de teste
- Tabelas: agent_sessions, conversations, document_embeddings

Uso:
    pytest tests/test_integration_db.py -v
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Generator
from uuid import uuid4

import psycopg2
import pytest

# ---------------------------------------------------------------------------
# Skip condicional: pula se DATABASE_URL de teste nao estiver configurado
# ou se a conexao falhar.
# ---------------------------------------------------------------------------

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/tcc_db_test",
)


def _is_db_available() -> bool:
    """Verifica se o banco de dados de teste esta acessivel."""
    try:
        conn = psycopg2.connect(TEST_DB_URL)
        conn.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _is_db_available(),
    reason=f"Database unavailable at {TEST_DB_URL} — set TEST_DATABASE_URL or start PostgreSQL",
)

# ---------------------------------------------------------------------------
# Fixtures de conexao e limpeza
# ---------------------------------------------------------------------------


@pytest.fixture
def db_conn() -> Generator[psycopg2.extensions.connection, None, None]:
    """Conexao direta com o banco de teste."""
    conn = psycopg2.connect(TEST_DB_URL)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def test_session_id() -> str:
    """ID unico de sessao para cada teste."""
    return f"integration-session-{uuid4()}"


@pytest.fixture
def test_project_id() -> str:
    """ID unico de projeto para cada teste."""
    return str(uuid4())


@pytest.fixture
def test_document_id() -> str:
    """ID unico de documento para cada teste."""
    return f"integration-doc-{uuid4()}"


# ---------------------------------------------------------------------------
# Helpers de limpeza
# ---------------------------------------------------------------------------


def _cleanup_session(conn: psycopg2.extensions.connection, session_id: str) -> None:
    """Remove sessao e conversas associadas."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM conversations WHERE session_id = %s", (session_id,))
        cur.execute("DELETE FROM agent_sessions WHERE session_id = %s", (session_id,))
    conn.commit()


def _cleanup_embeddings(conn: psycopg2.extensions.connection, project_id: str) -> None:
    """Remove embeddings de um projeto."""
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM document_embeddings WHERE metadata->>'project_id' = %s",
            (project_id,),
        )
    conn.commit()


# ---------------------------------------------------------------------------
# Testes do session_repository
# ---------------------------------------------------------------------------


class TestSessionRepositoryIntegration:
    """Testes de integracao do session_repository com banco real."""

    def test_get_or_create_session_creates_new(
        self,
        db_conn: psycopg2.extensions.connection,
        test_session_id: str,
        test_project_id: str,
    ) -> None:
        """Cria nova sessao quando nao existe."""
        from app.infrastructure.database.session_repository import get_or_create_session

        result = get_or_create_session(
            session_id=test_session_id, project_id=test_project_id
        )

        assert result["session_id"] == test_session_id
        assert result["project_id"] == test_project_id
        assert result["memory"] == {}
        assert "created_at" in result

        _cleanup_session(db_conn, test_session_id)

    def test_get_or_create_session_returns_existing(
        self,
        db_conn: psycopg2.extensions.connection,
        test_session_id: str,
        test_project_id: str,
    ) -> None:
        """Retorna sessao existente sem recriar."""
        from app.infrastructure.database.session_repository import get_or_create_session

        # Primeira chamada: cria
        result1 = get_or_create_session(
            session_id=test_session_id, project_id=test_project_id
        )
        created_at = result1["created_at"]

        # Segunda chamada: retorna existente
        result2 = get_or_create_session(
            session_id=test_session_id, project_id=test_project_id
        )

        assert result2["session_id"] == test_session_id
        assert result2["created_at"] == created_at  # mesmo timestamp

        _cleanup_session(db_conn, test_session_id)

    def test_update_session_memory(
        self,
        db_conn: psycopg2.extensions.connection,
        test_session_id: str,
        test_project_id: str,
    ) -> None:
        """Atualiza memoria de sessao existente."""
        from app.infrastructure.database.session_repository import (
            get_or_create_session,
            update_session_memory,
        )

        # Criar sessao
        get_or_create_session(session_id=test_session_id, project_id=test_project_id)

        # Atualizar memoria
        new_memory = {"topics": ["rag", "embeddings"], "turn_count": 3}
        update_session_memory(session_id=test_session_id, memory=new_memory)

        # Verificar que memoria foi atualizada
        result = get_or_create_session(
            session_id=test_session_id, project_id=test_project_id
        )
        assert result["memory"]["topics"] == ["rag", "embeddings"]
        assert result["memory"]["turn_count"] == 3

        _cleanup_session(db_conn, test_session_id)

    def test_update_session_memory_raises_for_nonexistent(
        self,
        db_conn: psycopg2.extensions.connection,
    ) -> None:
        """Atualizar memoria de sessao inexistente levanta ValueError."""
        from app.infrastructure.database.session_repository import update_session_memory

        nonexistent_id = f"nonexistent-{uuid4()}"
        with pytest.raises(ValueError, match="nao encontrada"):
            update_session_memory(session_id=nonexistent_id, memory={"key": "value"})


# ---------------------------------------------------------------------------
# Testes do conversation_repository
# ---------------------------------------------------------------------------


class TestConversationRepositoryIntegration:
    """Testes de integracao do conversation_repository com banco real."""

    def test_save_and_get_message(
        self,
        db_conn: psycopg2.extensions.connection,
        test_session_id: str,
        test_project_id: str,
    ) -> None:
        """Salva e recupera mensagem de conversa."""
        from app.infrastructure.database.conversation_repository import (
            get_conversation_history,
            save_message,
        )

        # Salvar mensagem do usuario
        save_message(
            session_id=test_session_id,
            project_id=test_project_id,
            role="user",
            content="O que e RAG?",
        )

        # Salvar resposta do assistant com fontes
        sources = [
            {
                "document": "doc-1",
                "page": 3,
                "section": "Introduction",
                "score": 0.95,
            }
        ]
        save_message(
            session_id=test_session_id,
            project_id=test_project_id,
            role="assistant",
            content="RAG e Retrieval-Augmented Generation...",
            sources=sources,
        )

        # Recuperar historico
        history = get_conversation_history(session_id=test_session_id, limit=10)

        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "O que e RAG?"
        assert history[1]["role"] == "assistant"
        assert history[1]["sources"] == sources

        _cleanup_session(db_conn, test_session_id)

    def test_get_conversation_respects_limit(
        self,
        db_conn: psycopg2.extensions.connection,
        test_session_id: str,
        test_project_id: str,
    ) -> None:
        """Parametro limit restringe mensagens retornadas."""
        from app.infrastructure.database.conversation_repository import (
            get_conversation_history,
            save_message,
        )

        # Salvar 5 mensagens
        for i in range(5):
            save_message(
                session_id=test_session_id,
                project_id=test_project_id,
                role="user",
                content=f"Mensagem {i}",
            )

        # Recuperar com limit=2
        history = get_conversation_history(session_id=test_session_id, limit=2)

        assert len(history) == 2
        # Ordem cronologica: mais antigo primeiro dentro do limit
        assert history[0]["content"] == "Mensagem 3"
        assert history[1]["content"] == "Mensagem 4"

        _cleanup_session(db_conn, test_session_id)

    def test_get_conversation_empty_for_new_session(
        self,
        test_session_id: str,
    ) -> None:
        """Sessao sem mensagens retorna lista vazia."""
        from app.infrastructure.database.conversation_repository import (
            get_conversation_history,
        )

        history = get_conversation_history(session_id=test_session_id)
        assert history == []


# ---------------------------------------------------------------------------
# Testes do PgVectorStore
# ---------------------------------------------------------------------------


class TestPgVectorStoreIntegration:
    """Testes de integracao do PgVectorStore com banco real."""

    def test_insert_and_search_embeddings(
        self,
        db_conn: psycopg2.extensions.connection,
        test_project_id: str,
        test_document_id: str,
    ) -> None:
        """Insere embeddings e busca por similaridade."""
        from app.infrastructure.database.pgvector_store import PgVectorStore

        store = PgVectorStore()

        # Criar embeddings de teste (vetores de 1536 dimensoes - OpenAI text-embedding-3-small)
        # Usar vetores simples para teste
        dim = 1536
        embedding_1 = [0.1] * dim
        embedding_2 = [0.2] * dim
        embedding_3 = [0.9] * dim  # muito diferente

        embeddings_data = [
            {
                "content": "RAG combina retriever e gerador de texto.",
                "embedding": embedding_1,
                "metadata": {
                    "project_id": test_project_id,
                    "document_id": test_document_id,
                    "page_number": 1,
                    "chunk_index": 0,
                },
            },
            {
                "content": "Embeddings sao representacoes vetoriais de texto.",
                "embedding": embedding_2,
                "metadata": {
                    "project_id": test_project_id,
                    "document_id": test_document_id,
                    "page_number": 1,
                    "chunk_index": 1,
                },
            },
        ]

        # Inserir
        count = store.insert_embeddings(embeddings_data)
        assert count == 2

        # Buscar com embedding similar ao primeiro
        query_embedding = [0.11] * dim  # proximo de embedding_1
        results = store.search_similar(
            project_id=test_project_id, query_embedding=query_embedding, top_k=2
        )

        assert len(results) == 2
        # O mais similar deve ser o primeiro inserido
        assert "RAG combina retriever" in results[0]["content"]
        assert "score" in results[0]
        assert 0.0 <= results[0]["score"] <= 1.0

        store.close()
        _cleanup_embeddings(db_conn, test_project_id)

    def test_search_with_min_score_filter(
        self,
        db_conn: psycopg2.extensions.connection,
        test_project_id: str,
        test_document_id: str,
    ) -> None:
        """Busca com filtro de score minimo exclui resultados distantes."""
        from app.infrastructure.database.pgvector_store import PgVectorStore

        store = PgVectorStore()

        dim = 1536
        embedding_similar = [0.5] * dim
        embedding_dissimilar = [0.9] * dim

        embeddings_data = [
            {
                "content": "Texto similar a consulta.",
                "embedding": embedding_similar,
                "metadata": {
                    "project_id": test_project_id,
                    "document_id": test_document_id,
                    "page_number": 1,
                    "chunk_index": 0,
                },
            },
            {
                "content": "Texto muito diferente da consulta.",
                "embedding": embedding_dissimilar,
                "metadata": {
                    "project_id": test_project_id,
                    "document_id": test_document_id,
                    "page_number": 2,
                    "chunk_index": 0,
                },
            },
        ]

        store.insert_embeddings(embeddings_data)

        # Buscar com score minimo alto — deve filtrar o dissimilar
        query_embedding = [0.51] * dim
        results = store.search_similar_by_project(
            project_id=test_project_id,
            query_embedding=query_embedding,
            top_k=5,
            min_score=0.9,
        )

        # Pelo menos o similar deve estar presente
        assert len(results) >= 1
        assert all(r["score"] >= 0.9 for r in results)

        store.close()
        _cleanup_embeddings(db_conn, test_project_id)

    def test_insert_empty_returns_zero(
        self,
    ) -> None:
        """Inserir lista vazia retorna 0 sem erro."""
        from app.infrastructure.database.pgvector_store import PgVectorStore

        store = PgVectorStore()
        count = store.insert_embeddings([])
        assert count == 0
        store.close()

    def test_search_nonexistent_project_returns_empty(
        self,
    ) -> None:
        """Buscar em projeto sem embeddings retorna lista vazia."""
        from app.infrastructure.database.pgvector_store import PgVectorStore

        store = PgVectorStore()
        results = store.search_similar(
            project_id=f"nonexistent-{uuid4()}",
            query_embedding=[0.1] * 1536,
            top_k=5,
        )
        assert results == []
        store.close()
