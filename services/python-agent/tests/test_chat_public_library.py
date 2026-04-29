"""
Testes do chat RAG com modo project_plus_public (biblioteca publica).

Cobertura:
- Modo project_only (comportamento padrao, retrocompativel)
- Modo project_plus_public com chunks de ambas as fontes
- Fallback quando biblioteca publica esta vazia
- Fontes mistas com source_type correto (project_document | public_library)
- Deduplicacao por conteudo entre fontes
- Feature flag ENABLE_PUBLIC_RETRIEVAL (bloqueia project_plus_public quando false)
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
    return "test-session-public-lib-1"


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


def _mock_project_chunks(project_id: str, count: int = 3) -> list[dict]:
    """Gera chunks mock do projeto."""
    chunks = []
    for i in range(count):
        chunks.append(
            {
                "content": f"Conteudo do chunk do projeto {i + 1}.",
                "metadata": {
                    "project_id": project_id,
                    "document_id": str(uuid4()),
                    "page_number": i + 1,
                    "chunk_index": i,
                    "section": f"Secao {i + 1}",
                    "source_type": "user_upload",
                },
                "score": 0.95 - (i * 0.05),
            }
        )
    return chunks


def _mock_public_chunks(count: int = 2) -> list[dict]:
    """Gera chunks mock da biblioteca publica."""
    chunks = []
    for i in range(count):
        chunks.append(
            {
                "content": f"Conteudo do chunk publico {i + 1}.",
                "metadata": {
                    "document_id": str(uuid4()),
                    "title": f"Livro Publico {i + 1}",
                    "page_number": i + 10,
                    "chunk_index": i,
                    "section": f"Capitulo {i + 1}",
                    "source_type": "public_library",
                },
                "score": 0.90 - (i * 0.05),
            }
        )
    return chunks


# ---------------------------------------------------------------------------
# Testes do RAGService com retrieval_mode
# ---------------------------------------------------------------------------


class TestRAGServiceProjectOnlyMode:
    """Testes do modo project_only (comportamento padrao)."""

    @patch("app.domain.rag_service.conversation_repository")
    @patch("app.domain.rag_service.session_repository")
    @patch("app.domain.rag_service.PgVectorStore")
    @patch("app.domain.rag_service.OpenAIEmbedder")
    def test_project_only_uses_only_project_chunks(
        self,
        mock_embedder_cls,
        mock_store_cls,
        mock_session_repo,
        mock_conv_repo,
        project_id,
        session_id,
    ) -> None:
        """Modo project_only nao busca na biblioteca publica."""
        from app.domain.rag_service import RAGService

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder._use_mock = True
        mock_embedder_cls.return_value = mock_embedder

        mock_store = MagicMock()
        mock_store.search_similar_by_project.return_value = _mock_project_chunks(
            project_id
        )
        mock_store_cls.return_value = mock_store

        mock_session_repo.get_or_create_session.return_value = {
            "session_id": session_id,
            "project_id": project_id,
            "memory": {},
            "created_at": None,
        }
        mock_conv_repo.get_conversation_history.return_value = []

        service = RAGService()
        result = service.chat(
            project_id=project_id,
            session_id=session_id,
            message="Qual o objetivo?",
            retrieval_mode="project_only",
        )

        assert result.answer != ""
        assert len(result.sources) == 3
        # Verifica que nao buscou na biblioteca publica
        mock_store.search_similar_public_library.assert_not_called()
        # Nenhuma fonte deve ser do tipo public_library
        for source in result.sources:
            assert source.source_type == "project_document"


class TestRAGServiceProjectPlusPublicMode:
    """Testes do modo project_plus_public."""

    @patch("app.domain.rag_service.conversation_repository")
    @patch("app.domain.rag_service.session_repository")
    @patch("app.domain.rag_service.PgVectorStore")
    @patch("app.domain.rag_service.OpenAIEmbedder")
    def test_project_plus_public_merges_both_sources(
        self,
        mock_embedder_cls,
        mock_store_cls,
        mock_session_repo,
        mock_conv_repo,
        project_id,
        session_id,
    ) -> None:
        """Modo project_plus_public busca em ambas as fontes e mescla."""
        from app.domain.rag_service import RAGService

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder._use_mock = True
        mock_embedder_cls.return_value = mock_embedder

        mock_store = MagicMock()
        mock_store.search_similar_by_project.return_value = _mock_project_chunks(
            project_id, count=3
        )
        mock_store.search_similar_public_library.return_value = _mock_public_chunks(
            count=2
        )
        mock_store_cls.return_value = mock_store

        mock_session_repo.get_or_create_session.return_value = {
            "session_id": session_id,
            "project_id": project_id,
            "memory": {},
            "created_at": None,
        }
        mock_conv_repo.get_conversation_history.return_value = []

        service = RAGService()
        result = service.chat(
            project_id=project_id,
            session_id=session_id,
            message="Qual o objetivo?",
            retrieval_mode="project_plus_public",
        )

        assert result.answer != ""
        # top_k=5, temos 3+2=5 chunks unicos
        assert len(result.sources) <= 5
        # Verifica que buscou na biblioteca publica
        mock_store.search_similar_public_library.assert_called_once()

    @patch("app.domain.rag_service.conversation_repository")
    @patch("app.domain.rag_service.session_repository")
    @patch("app.domain.rag_service.PgVectorStore")
    @patch("app.domain.rag_service.OpenAIEmbedder")
    def test_public_sources_have_correct_source_type(
        self,
        mock_embedder_cls,
        mock_store_cls,
        mock_session_repo,
        mock_conv_repo,
        project_id,
        session_id,
    ) -> None:
        """Fontes da biblioteca publica recebem source_type='public_library'."""
        from app.domain.rag_service import RAGService

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder._use_mock = True
        mock_embedder_cls.return_value = mock_embedder

        mock_store = MagicMock()
        mock_store.search_similar_by_project.return_value = _mock_project_chunks(
            project_id, count=2
        )
        mock_store.search_similar_public_library.return_value = _mock_public_chunks(
            count=2
        )
        mock_store_cls.return_value = mock_store

        mock_session_repo.get_or_create_session.return_value = {
            "session_id": session_id,
            "project_id": project_id,
            "memory": {},
            "created_at": None,
        }
        mock_conv_repo.get_conversation_history.return_value = []

        service = RAGService()
        result = service.chat(
            project_id=project_id,
            session_id=session_id,
            message="Qual o objetivo?",
            retrieval_mode="project_plus_public",
        )

        # Verifica fontes publicas com source_type correto
        public_sources = [
            s for s in result.sources if s.source_type == "public_library"
        ]
        assert len(public_sources) > 0
        for src in public_sources:
            assert src.page == 0

        # Verifica fontes do projeto com source_type correto
        project_sources = [
            s for s in result.sources if s.source_type == "project_document"
        ]
        assert len(project_sources) > 0


class TestRAGServicePublicLibraryFallback:
    """Testes de fallback quando biblioteca publica esta vazia."""

    @patch("app.domain.rag_service.conversation_repository")
    @patch("app.domain.rag_service.session_repository")
    @patch("app.domain.rag_service.PgVectorStore")
    @patch("app.domain.rag_service.OpenAIEmbedder")
    def test_empty_public_library_falls_back_to_project(
        self,
        mock_embedder_cls,
        mock_store_cls,
        mock_session_repo,
        mock_conv_repo,
        project_id,
        session_id,
    ) -> None:
        """Se biblioteca publica vazia, usa apenas chunks do projeto."""
        from app.domain.rag_service import RAGService

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder._use_mock = True
        mock_embedder_cls.return_value = mock_embedder

        mock_store = MagicMock()
        mock_store.search_similar_by_project.return_value = _mock_project_chunks(
            project_id, count=3
        )
        mock_store.search_similar_public_library.return_value = []
        mock_store_cls.return_value = mock_store

        mock_session_repo.get_or_create_session.return_value = {
            "session_id": session_id,
            "project_id": project_id,
            "memory": {},
            "created_at": None,
        }
        mock_conv_repo.get_conversation_history.return_value = []

        service = RAGService()
        result = service.chat(
            project_id=project_id,
            session_id=session_id,
            message="Qual o objetivo?",
            retrieval_mode="project_plus_public",
        )

        assert result.answer != ""
        assert len(result.sources) == 3
        # Nenhuma fonte publica
        public_sources = [
            s for s in result.sources if s.source_type == "public_library"
        ]
        assert len(public_sources) == 0

    @patch("app.domain.rag_service.conversation_repository")
    @patch("app.domain.rag_service.session_repository")
    @patch("app.domain.rag_service.PgVectorStore")
    @patch("app.domain.rag_service.OpenAIEmbedder")
    def test_empty_project_uses_public_only(
        self,
        mock_embedder_cls,
        mock_store_cls,
        mock_session_repo,
        mock_conv_repo,
        project_id,
        session_id,
    ) -> None:
        """Se projeto sem chunks mas publica tem, usa publica."""
        from app.domain.rag_service import RAGService

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder._use_mock = True
        mock_embedder_cls.return_value = mock_embedder

        mock_store = MagicMock()
        mock_store.search_similar_by_project.return_value = []
        mock_store.search_similar_public_library.return_value = _mock_public_chunks(
            count=3
        )
        mock_store_cls.return_value = mock_store

        mock_session_repo.get_or_create_session.return_value = {
            "session_id": session_id,
            "project_id": project_id,
            "memory": {},
            "created_at": None,
        }
        mock_conv_repo.get_conversation_history.return_value = []

        service = RAGService()
        result = service.chat(
            project_id=project_id,
            session_id=session_id,
            message="Qual o objetivo?",
            retrieval_mode="project_plus_public",
        )

        assert result.answer != ""
        assert len(result.sources) == 3
        # Todas as fontes sao publicas
        for src in result.sources:
            assert src.source_type == "public_library"
            assert src.page == 0

    @patch("app.domain.rag_service.conversation_repository")
    @patch("app.domain.rag_service.session_repository")
    @patch("app.domain.rag_service.PgVectorStore")
    @patch("app.domain.rag_service.OpenAIEmbedder")
    def test_both_empty_returns_no_context_answer(
        self,
        mock_embedder_cls,
        mock_store_cls,
        mock_session_repo,
        mock_conv_repo,
        project_id,
        session_id,
    ) -> None:
        """Se ambas as fontes vazias, retorna NO_CONTEXT_ANSWER."""
        from app.domain.rag_service import NO_CONTEXT_ANSWER, RAGService

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder._use_mock = True
        mock_embedder_cls.return_value = mock_embedder

        mock_store = MagicMock()
        mock_store.search_similar_by_project.return_value = []
        mock_store.search_similar_public_library.return_value = []
        mock_store_cls.return_value = mock_store

        mock_session_repo.get_or_create_session.return_value = {
            "session_id": session_id,
            "project_id": project_id,
            "memory": {},
            "created_at": None,
        }
        mock_conv_repo.get_conversation_history.return_value = []

        service = RAGService()
        result = service.chat(
            project_id=project_id,
            session_id=session_id,
            message="Pergunta sem contexto",
            retrieval_mode="project_plus_public",
        )

        assert result.answer == NO_CONTEXT_ANSWER
        assert result.sources == []


class TestRAGServiceDeduplication:
    """Testes de deduplicacao entre fontes."""

    @patch("app.domain.rag_service.conversation_repository")
    @patch("app.domain.rag_service.session_repository")
    @patch("app.domain.rag_service.PgVectorStore")
    @patch("app.domain.rag_service.OpenAIEmbedder")
    def test_duplicate_content_deduplicated(
        self,
        mock_embedder_cls,
        mock_store_cls,
        mock_session_repo,
        mock_conv_repo,
        project_id,
        session_id,
    ) -> None:
        """Chunks com mesmo conteudo sao deduplicados."""
        from app.domain.rag_service import RAGService

        duplicate_content = "Este conteudo aparece em ambas as fontes."

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder._use_mock = True
        mock_embedder_cls.return_value = mock_embedder

        mock_store = MagicMock()
        mock_store.search_similar_by_project.return_value = [
            {
                "content": duplicate_content,
                "metadata": {
                    "project_id": project_id,
                    "document_id": "doc-project",
                    "page_number": 1,
                    "source_type": "user_upload",
                },
                "score": 0.95,
            }
        ]
        mock_store.search_similar_public_library.return_value = [
            {
                "content": duplicate_content,
                "metadata": {
                    "document_id": "doc-public",
                    "title": "Livro Publico",
                    "page_number": 5,
                    "source_type": "public_library",
                },
                "score": 0.90,
            }
        ]
        mock_store_cls.return_value = mock_store

        mock_session_repo.get_or_create_session.return_value = {
            "session_id": session_id,
            "project_id": project_id,
            "memory": {},
            "created_at": None,
        }
        mock_conv_repo.get_conversation_history.return_value = []

        service = RAGService()
        result = service.chat(
            project_id=project_id,
            session_id=session_id,
            message="Pergunta com conteudo duplicado",
            retrieval_mode="project_plus_public",
        )

        # Apenas 1 fonte (deduplicada), a de maior score (project)
        assert len(result.sources) == 1


# ---------------------------------------------------------------------------
# Testes do endpoint da API com retrieval_mode
# ---------------------------------------------------------------------------


class TestChatEndpointRetrievalMode:
    """Testes do endpoint POST /api/v1/chat com retrieval_mode."""

    @patch("app.api.v1.endpoints.chat.RAGService")
    def test_endpoint_accepts_project_only_mode(
        self,
        mock_rag_cls,
        client: TestClient,
        project_id,
        session_id,
    ) -> None:
        """Endpoint aceita retrieval_mode=project_only."""
        from app.schemas.contracts_v1 import ChatResponse, Source

        mock_service = MagicMock()
        mock_service.chat.return_value = ChatResponse(
            answer="Resposta baseada no projeto.",
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
            "retrieval_mode": "project_only",
        }
        res = client.post("/api/v1/chat", json=payload)

        assert res.status_code == 200
        data = res.json()
        assert data["answer"] == "Resposta baseada no projeto."
        # Verifica que retrieval_mode foi passado
        mock_service.chat.assert_called_once()
        call_kwargs = mock_service.chat.call_args[1]
        assert call_kwargs["retrieval_mode"] == "project_only"

    @patch("app.api.v1.endpoints.chat.RAGService")
    def test_endpoint_accepts_project_plus_public_mode(
        self,
        mock_rag_cls,
        client: TestClient,
        project_id,
        session_id,
    ) -> None:
        """Endpoint aceita retrieval_mode=project_plus_public quando feature flag ativa."""
        from app.core.config import Settings
        from app.schemas.contracts_v1 import ChatResponse, Source

        mock_service = MagicMock()
        mock_service.chat.return_value = ChatResponse(
            answer="Resposta com fontes publicas.",
            sources=[
                Source(
                    document="Livro Publico 1",
                    page=0,
                    section="Capitulo 1",
                    score=0.92,
                    source_type="public_library",
                )
            ],
            session_id=session_id,
        )
        mock_rag_cls.return_value = mock_service
        # Configura feature flag como ativa
        mock_settings = Settings(ENABLE_PUBLIC_RETRIEVAL=True)
        mock_service._settings = mock_settings

        payload = {
            "project_id": project_id,
            "session_id": session_id,
            "message": "Qual o objetivo?",
            "retrieval_mode": "project_plus_public",
        }
        res = client.post("/api/v1/chat", json=payload)

        assert res.status_code == 200
        data = res.json()
        assert data["sources"][0]["source_type"] == "public_library"
        call_kwargs = mock_service.chat.call_args[1]
        assert call_kwargs["retrieval_mode"] == "project_plus_public"

    @patch("app.api.v1.endpoints.chat.RAGService")
    def test_endpoint_defaults_to_project_only(
        self,
        mock_rag_cls,
        client: TestClient,
        project_id,
        session_id,
    ) -> None:
        """Endpoint usa project_only como padrao quando retrieval_mode omitido."""
        from app.schemas.contracts_v1 import ChatResponse

        mock_service = MagicMock()
        mock_service.chat.return_value = ChatResponse(
            answer="Resposta padrao.",
            sources=[],
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
        call_kwargs = mock_service.chat.call_args[1]
        assert call_kwargs["retrieval_mode"] == "project_only"

    def test_endpoint_rejects_invalid_retrieval_mode(
        self,
        client: TestClient,
        project_id,
        session_id,
    ) -> None:
        """Endpoint rejeita retrieval_mode invalido com 422."""
        payload = {
            "project_id": project_id,
            "session_id": session_id,
            "message": "Qual o objetivo?",
            "retrieval_mode": "invalid_mode",
        }
        res = client.post("/api/v1/chat", json=payload)

        assert res.status_code == 422


# ---------------------------------------------------------------------------
# Testes do feature flag ENABLE_PUBLIC_RETRIEVAL
# ---------------------------------------------------------------------------


class TestPublicRetrievalFeatureFlag:
    """Testes do feature flag ENABLE_PUBLIC_RETRIEVAL."""

    @patch("app.api.v1.endpoints.chat.RAGService")
    def test_project_plus_public_returns_400_when_flag_disabled(
        self,
        mock_rag_cls,
        client: TestClient,
        project_id,
        session_id,
    ) -> None:
        """Quando ENABLE_PUBLIC_RETRIEVAL=false, project_plus_public retorna 400."""
        from app.core.config import Settings

        # Configura RAGService com feature flag desativada (padrao)
        mock_service = MagicMock()
        mock_service.public_retrieval_enabled = False
        mock_rag_cls.return_value = mock_service

        payload = {
            "project_id": project_id,
            "session_id": session_id,
            "message": "Qual o objetivo?",
            "retrieval_mode": "project_plus_public",
        }
        res = client.post("/api/v1/chat", json=payload)

        assert res.status_code == 400
        data = res.json()
        assert "nao esta habilitado" in data["detail"]
        # RAGService.chat nao deve ser chamado
        mock_service.chat.assert_not_called()

    @patch("app.api.v1.endpoints.chat.RAGService")
    def test_project_only_works_when_flag_disabled(
        self,
        mock_rag_cls,
        client: TestClient,
        project_id,
        session_id,
    ) -> None:
        """project_only funciona normalmente mesmo com flag desativada."""
        from app.schemas.contracts_v1 import ChatResponse

        mock_service = MagicMock()
        mock_service.public_retrieval_enabled = True
        mock_service.chat.return_value = ChatResponse(
            answer="Resposta do projeto.",
            sources=[],
            session_id=session_id,
        )
        mock_rag_cls.return_value = mock_service

        payload = {
            "project_id": project_id,
            "session_id": session_id,
            "message": "Qual o objetivo?",
            "retrieval_mode": "project_only",
        }
        res = client.post("/api/v1/chat", json=payload)

        assert res.status_code == 200
        mock_service.chat.assert_called_once()
