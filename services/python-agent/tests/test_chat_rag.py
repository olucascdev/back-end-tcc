"""
Testes do chat RAG com fontes.

Cobertura:
- Chat com contexto relevante (mock de pgvector + LLM)
- Chat sem contexto (limitacao explicita)
- Formato de resposta com fontes
- Persistencia de historico de sessao
- Tratamento de erro do LLM
- Endpoint da API com mocks completos
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    """Cliente de teste reutilizavel."""
    return TestClient(app)


@pytest.fixture
def project_id() -> str:
    """UUID de projeto para testes."""
    return str(uuid4())


@pytest.fixture
def session_id() -> str:
    """ID de sessao para testes."""
    return "test-session-rag-1"


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


def _mock_chunks(project_id: str, count: int = 3) -> list[dict]:
    """Gera chunks mock com metadata e score."""
    chunks = []
    for i in range(count):
        chunks.append(
            {
                "content": f"Conteudo do chunk {i + 1} sobre o tema do documento.",
                "metadata": {
                    "project_id": project_id,
                    "document_id": str(uuid4()),
                    "page_number": i + 1,
                    "chunk_index": i,
                    "section": f"Secao {i + 1}",
                },
                "score": 0.95 - (i * 0.05),
            }
        )
    return chunks


# ---------------------------------------------------------------------------
# Testes unitarios do RAGService
# ---------------------------------------------------------------------------


class TestRAGServiceWithContext:
    """Testes do RAGService quando ha contexto relevante."""

    @patch("app.domain.rag_service.PgVectorStore")
    @patch("app.domain.rag_service.OpenAIEmbedder")
    def test_chat_returns_answer_with_sources(
        self,
        mock_embedder_cls,
        mock_store_cls,
        project_id,
        session_id,
    ) -> None:
        """Chat com contexto retorna resposta e fontes."""
        from app.domain.rag_service import RAGService

        # Configura mocks
        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder._use_mock = True
        mock_embedder_cls.return_value = mock_embedder

        mock_store = MagicMock()
        mock_store.search_similar_by_project.return_value = _mock_chunks(project_id)
        mock_store_cls.return_value = mock_store

        service = RAGService()
        result = service.chat(
            project_id=project_id,
            session_id=session_id,
            message="Qual o objetivo deste documento?",
        )

        # Verifica resposta
        assert result.answer != ""
        assert len(result.sources) == 3
        assert result.session_id == session_id

        # Verifica fontes
        for source in result.sources:
            assert source.document != ""
            assert source.page >= 1
            assert source.score > 0.7

        # Verifica chamadas
        mock_embedder.embed_query.assert_called_once_with(
            "Qual o objetivo deste documento?"
        )
        mock_store.search_similar_by_project.assert_called_once()

    @patch("app.domain.rag_service.PgVectorStore")
    @patch("app.domain.rag_service.OpenAIEmbedder")
    def test_chat_preserves_session_history(
        self,
        mock_embedder_cls,
        mock_store_cls,
        project_id,
    ) -> None:
        """Historico da sessao e preservado entre chamadas."""
        from app.domain.rag_service import RAGService

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder._use_mock = True
        mock_embedder_cls.return_value = mock_embedder

        mock_store = MagicMock()
        mock_store.search_similar_by_project.return_value = _mock_chunks(project_id)
        mock_store_cls.return_value = mock_store

        service = RAGService()
        session = "session-history-test"

        # Primeira chamada
        result1 = service.chat(
            project_id=project_id,
            session_id=session,
            message="Pergunta 1",
        )
        assert result1.session_id == session

        # Segunda chamada — historico deve incluir primeira troca
        result2 = service.chat(
            project_id=project_id,
            session_id=session,
            message="Pergunta 2",
        )
        assert result2.session_id == session

        # Verifica que historico tem 4 mensagens (2 user + 2 assistant)
        history = service._session_history.get_history(session)
        assert len(history) == 4
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "Pergunta 1"
        assert history[1]["role"] == "assistant"
        assert history[2]["role"] == "user"
        assert history[2]["content"] == "Pergunta 2"


class TestRAGServiceWithoutContext:
    """Testes do RAGService quando nao ha contexto relevante."""

    @patch("app.domain.rag_service.PgVectorStore")
    @patch("app.domain.rag_service.OpenAIEmbedder")
    def test_chat_returns_limitation_when_no_chunks(
        self,
        mock_embedder_cls,
        mock_store_cls,
        project_id,
        session_id,
    ) -> None:
        """Sem chunks relevantes → retorna limitacao explicita."""
        from app.domain.rag_service import RAGService, NO_CONTEXT_ANSWER

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder._use_mock = True
        mock_embedder_cls.return_value = mock_embedder

        mock_store = MagicMock()
        mock_store.search_similar_by_project.return_value = []
        mock_store_cls.return_value = mock_store

        service = RAGService()
        result = service.chat(
            project_id=project_id,
            session_id=session_id,
            message="Pergunta sem contexto",
        )

        assert result.answer == NO_CONTEXT_ANSWER
        assert result.sources == []
        assert result.session_id == session_id

    @patch("app.domain.rag_service.PgVectorStore")
    @patch("app.domain.rag_service.OpenAIEmbedder")
    def test_chat_returns_limitation_when_low_score(
        self,
        mock_embedder_cls,
        mock_store_cls,
        project_id,
        session_id,
    ) -> None:
        """Chunks com score baixo filtrados pelo store → retorna limitacao."""
        from app.domain.rag_service import RAGService, NO_CONTEXT_ANSWER

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder._use_mock = True
        mock_embedder_cls.return_value = mock_embedder

        # Store ja filtra por min_score; retorna vazio quando tudo esta abaixo
        mock_store = MagicMock()
        mock_store.search_similar_by_project.return_value = []
        mock_store_cls.return_value = mock_store

        service = RAGService()
        result = service.chat(
            project_id=project_id,
            session_id=session_id,
            message="Pergunta com contexto fraco",
        )

        assert result.answer == NO_CONTEXT_ANSWER
        assert result.sources == []


class TestRAGServiceSourceFormat:
    """Testes do formato de fontes na resposta."""

    @patch("app.domain.rag_service.PgVectorStore")
    @patch("app.domain.rag_service.OpenAIEmbedder")
    def test_sources_have_correct_format(
        self,
        mock_embedder_cls,
        mock_store_cls,
        project_id,
        session_id,
    ) -> None:
        """Fontes possuem campos document, page, section, score."""
        from app.domain.rag_service import RAGService

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder._use_mock = True
        mock_embedder_cls.return_value = mock_embedder

        doc_id = str(uuid4())
        chunks = [
            {
                "content": "Texto importante sobre metodologia.",
                "metadata": {
                    "project_id": project_id,
                    "document_id": doc_id,
                    "page_number": 5,
                    "section": "Metodologia",
                },
                "score": 0.92,
            }
        ]
        mock_store = MagicMock()
        mock_store.search_similar_by_project.return_value = chunks
        mock_store_cls.return_value = mock_store

        service = RAGService()
        result = service.chat(
            project_id=project_id,
            session_id=session_id,
            message="Qual a metodologia usada?",
        )

        assert len(result.sources) == 1
        source = result.sources[0]
        assert source.document == doc_id
        assert source.page == 5
        assert source.section == "Metodologia"
        assert source.score == 0.92


class TestRAGServiceLLMError:
    """Testes de erro ao chamar LLM."""

    @patch("openai.OpenAI")
    @patch("app.domain.rag_service.PgVectorStore")
    @patch("app.domain.rag_service.OpenAIEmbedder")
    def test_llm_error_raises_llm_error(
        self,
        mock_embedder_cls,
        mock_store_cls,
        mock_openai_cls,
        project_id,
        session_id,
    ) -> None:
        """Erro na API OpenAI levanta LLMError."""
        from app.domain.rag_service import LLMError, RAGService
        from app.core.config import Settings

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder._use_mock = False  # Forca uso real do LLM
        mock_embedder_cls.return_value = mock_embedder

        mock_store = MagicMock()
        mock_store.search_similar_by_project.return_value = _mock_chunks(project_id)
        mock_store_cls.return_value = mock_store

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API error")
        mock_openai_cls.return_value = mock_client

        settings = Settings(OPENAI_API_KEY="fake-key")
        service = RAGService(settings=settings)

        with pytest.raises(LLMError, match="Falha ao gerar resposta"):
            service.chat(
                project_id=project_id,
                session_id=session_id,
                message="Pergunta que causa erro",
            )


# ---------------------------------------------------------------------------
# Testes do endpoint da API
# ---------------------------------------------------------------------------


class TestChatEndpoint:
    """Testes do endpoint POST /api/v1/chat com mocks."""

    @patch("app.api.v1.endpoints.chat.RAGService")
    def test_chat_endpoint_returns_response_with_sources(
        self,
        mock_rag_cls,
        client: TestClient,
        project_id,
        session_id,
    ) -> None:
        """Endpoint retorna resposta com fontes."""
        from app.schemas.contracts_v1 import ChatResponse, Source

        mock_service = MagicMock()
        mock_service.chat.return_value = ChatResponse(
            answer="Resposta baseada no contexto.",
            sources=[
                Source(
                    document=str(uuid4()),
                    page=1,
                    section="Introducao",
                    score=0.95,
                )
            ],
            session_id=session_id,
        )
        mock_rag_cls.return_value = mock_service

        payload = {
            "project_id": project_id,
            "session_id": session_id,
            "message": "Qual o objetivo?",
        }
        res = client.post("/api/v1/chat", json=payload)

        assert res.status_code == 200
        data = res.json()
        assert data["answer"] == "Resposta baseada no contexto."
        assert len(data["sources"]) == 1
        assert data["sources"][0]["page"] == 1
        assert data["session_id"] == session_id

    @patch("app.api.v1.endpoints.chat.RAGService")
    def test_chat_endpoint_returns_limitation_without_context(
        self,
        mock_rag_cls,
        client: TestClient,
        project_id,
        session_id,
    ) -> None:
        """Endpoint retorna limitacao quando sem contexto."""
        from app.domain.rag_service import NO_CONTEXT_ANSWER
        from app.schemas.contracts_v1 import ChatResponse

        mock_service = MagicMock()
        mock_service.chat.return_value = ChatResponse(
            answer=NO_CONTEXT_ANSWER,
            sources=[],
            session_id=session_id,
        )
        mock_rag_cls.return_value = mock_service

        payload = {
            "project_id": project_id,
            "session_id": session_id,
            "message": "Pergunta sem contexto",
        }
        res = client.post("/api/v1/chat", json=payload)

        assert res.status_code == 200
        data = res.json()
        assert "Nao encontrei informacoes suficientes" in data["answer"]
        assert data["sources"] == []

    @patch("app.api.v1.endpoints.chat.RAGService")
    def test_chat_endpoint_handles_llm_error(
        self,
        mock_rag_cls,
        client: TestClient,
        project_id,
        session_id,
    ) -> None:
        """Endpoint retorna 502 quando LLM falha."""
        from app.domain.rag_service import LLMError

        mock_service = MagicMock()
        mock_service.chat.side_effect = LLMError("Falha ao gerar resposta")
        mock_rag_cls.return_value = mock_service

        payload = {
            "project_id": project_id,
            "session_id": session_id,
            "message": "Pergunta que causa erro",
        }
        res = client.post("/api/v1/chat", json=payload)

        assert res.status_code == 502
        data = res.json()
        assert "detail" in data

    def test_chat_endpoint_validation_error(self, client: TestClient) -> None:
        """Endpoint retorna 422 para payload invalido."""
        payload = {
            "project_id": "not-a-uuid",
            "session_id": "",
            "message": "",
        }
        res = client.post("/api/v1/chat", json=payload)

        assert res.status_code == 422


# ---------------------------------------------------------------------------
# Testes unitarios de componentes de infraestrutura
# ---------------------------------------------------------------------------


class TestOpenAIEmbedderQuery:
    """Testes do metodo embed_query."""

    def test_embed_query_mock_returns_vector(self) -> None:
        """embed_query retorna vetor de dimensao correta."""
        from app.infrastructure.embeddings.openai_embedder import OpenAIEmbedder

        embedder = OpenAIEmbedder()  # usa mock
        embedding = embedder.embed_query("teste de consulta")

        assert len(embedding) == 1536
        assert isinstance(embedding, list)

    def test_embed_query_mock_consistent(self) -> None:
        """Mesmo texto retorna mesmo embedding."""
        from app.infrastructure.embeddings.openai_embedder import OpenAIEmbedder

        embedder = OpenAIEmbedder()
        e1 = embedder.embed_query("texto fixo")
        e2 = embedder.embed_query("texto fixo")

        assert e1 == e2


class TestPgVectorStoreSearchByProject:
    """Testes do metodo search_similar_by_project."""

    @patch("app.infrastructure.database.pgvector_store.ThreadedConnectionPool")
    def test_search_filters_by_min_score(self, mock_pool_cls) -> None:
        """Filtra resultados abaixo do score minimo."""
        from app.infrastructure.database.pgvector_store import PgVectorStore

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        # Retorna 3 rows: 2 acima e 1 abaixo do threshold
        mock_cursor.fetchall.return_value = [
            (
                "chunk alto 1",
                {"project_id": "p1", "document_id": "d1"},
                0.05,
            ),  # score 0.95
            (
                "chunk alto 2",
                {"project_id": "p1", "document_id": "d2"},
                0.15,
            ),  # score 0.85
            (
                "chunk baixo",
                {"project_id": "p1", "document_id": "d3"},
                0.35,
            ),  # score 0.65
        ]
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.commit = MagicMock()
        mock_pool = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_pool_cls.return_value = mock_pool

        store = PgVectorStore()
        results = store.search_similar_by_project(
            project_id="p1",
            query_embedding=[0.1] * 1536,
            top_k=5,
            min_score=0.7,
        )

        assert len(results) == 2
        assert results[0]["score"] == 0.95
        assert results[1]["score"] == 0.85

    @patch("app.infrastructure.database.pgvector_store.ThreadedConnectionPool")
    def test_search_empty_results(self, mock_pool_cls) -> None:
        """Sem resultados retorna lista vazia."""
        from app.infrastructure.database.pgvector_store import PgVectorStore

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_pool = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_pool_cls.return_value = mock_pool

        store = PgVectorStore()
        results = store.search_similar_by_project(
            project_id="p1",
            query_embedding=[0.1] * 1536,
        )

        assert results == []
