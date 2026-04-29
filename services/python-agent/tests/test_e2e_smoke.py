"""
Testes e2e smoke para pipeline completo: upload → process → chat → verify sources.

Cobertura:
- Fluxo completo com ambos retrieval_mode (project_only, project_plus_public)
- Mock de dependencias externas (OpenAI, MinIO)
- Verificacao de fontes na resposta
- Validacao de contratos entre Go gateway e Python agent
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.contracts_v1 import ChatResponse, Source


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client() -> TestClient:
    """Cliente de teste para a API Python."""
    return TestClient(app)


@pytest.fixture
def project_id() -> str:
    """UUID de projeto para testes."""
    return str(uuid.uuid4())


@pytest.fixture
def document_id() -> str:
    """UUID de documento para testes."""
    return str(uuid.uuid4())


@pytest.fixture
def session_id() -> str:
    """ID de sessao de chat."""
    return "e2e-smoke-session"


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
                    "document_id": str(uuid.uuid4()),
                    "page_number": i + 1,
                    "chunk_index": i,
                    "section": f"Secao {i + 1}",
                },
                "score": 0.95 - (i * 0.05),
            }
        )
    return chunks


def _mock_public_chunks(count: int = 2) -> list[dict]:
    """Gera chunks mock simulando acervo publico."""
    chunks = []
    public_docs = [
        "pedagogy-foundations.pdf",
        "learning-theories-handbook.pdf",
    ]
    for i in range(count):
        chunks.append(
            {
                "content": f"Conteudo do acervo publico {i + 1}.",
                "metadata": {
                    "project_id": "public-library",
                    "document_id": public_docs[i],
                    "page_number": (i + 1) * 10,
                    "chunk_index": i,
                    "section": f"Capitulo {i + 1}",
                    "source_type": "public_library",
                },
                "score": 0.88 - (i * 0.03),
            }
        )
    return chunks


# ---------------------------------------------------------------------------
# E2E Smoke: Project Only
# ---------------------------------------------------------------------------


class TestE2EProjectOnly:
    """Testes e2e com retrieval_mode project_only."""

    @patch("app.api.v1.endpoints.chat.RAGService")
    def test_full_pipeline_project_only(
        self,
        mock_rag_cls,
        client: TestClient,
        project_id: str,
        session_id: str,
    ) -> None:
        """Pipeline completo: chat com project_only retorna fontes do projeto."""
        from app.domain.rag_service import RAGService

        # Configurar mock do RAGService
        mock_service = MagicMock(spec=RAGService)
        mock_service.chat.return_value = ChatResponse(
            answer="Com base nos documentos do projeto, a metodologia utilizada e qualitativa.",
            sources=[
                Source(
                    document="project-thesis.pdf",
                    page=15,
                    section="Metodologia",
                    score=0.95,
                ),
                Source(
                    document="project-data.pdf",
                    page=3,
                    section="Resultados",
                    score=0.89,
                ),
            ],
            session_id=session_id,
        )
        mock_rag_cls.return_value = mock_service

        # 1. Chat com retrieval_mode project_only
        payload = {
            "project_id": project_id,
            "session_id": session_id,
            "message": "Qual a metodologia usada no projeto?",
            "retrieval_mode": "project_only",
        }
        res = client.post("/api/v1/chat", json=payload)

        assert res.status_code == 200
        data = res.json()

        # 2. Verificar resposta
        assert data["answer"] != ""
        assert "metodologia" in data["answer"].lower()

        # 3. Verificar fontes
        assert len(data["sources"]) == 2
        for source in data["sources"]:
            assert source["document"] != ""
            assert source["page"] >= 1
            assert source["score"] > 0.7
            assert source["source_type"] == "project_document"

        # 4. Verificar que RAGService foi chamado com parametros corretos
        mock_service.chat.assert_called_once()
        call_kwargs = mock_service.chat.call_args
        assert call_kwargs.kwargs["project_id"] == project_id
        assert call_kwargs.kwargs["session_id"] == session_id

    @patch("app.api.v1.endpoints.chat.RAGService")
    def test_project_only_no_context_returns_limitation(
        self,
        mock_rag_cls,
        client: TestClient,
        project_id: str,
        session_id: str,
    ) -> None:
        """Sem contexto no projeto → retorna limitacao explicita."""
        from app.domain.rag_service import NO_CONTEXT_ANSWER, RAGService

        mock_service = MagicMock(spec=RAGService)
        mock_service.chat.return_value = ChatResponse(
            answer=NO_CONTEXT_ANSWER,
            sources=[],
            session_id=session_id,
        )
        mock_rag_cls.return_value = mock_service

        payload = {
            "project_id": project_id,
            "session_id": session_id,
            "message": "Pergunta sobre tema nao coberto",
            "retrieval_mode": "project_only",
        }
        res = client.post("/api/v1/chat", json=payload)

        assert res.status_code == 200
        data = res.json()
        assert "Nao encontrei informacoes suficientes" in data["answer"]
        assert data["sources"] == []


# ---------------------------------------------------------------------------
# E2E Smoke: Project Plus Public
# ---------------------------------------------------------------------------


class TestE2EProjectPlusPublic:
    """Testes e2e com retrieval_mode project_plus_public."""

    @patch("app.api.v1.endpoints.chat.RAGService")
    def test_full_pipeline_project_plus_public(
        self,
        mock_rag_cls,
        client: TestClient,
        project_id: str,
        session_id: str,
    ) -> None:
        """Pipeline completo: chat com project_plus_public retorna fontes mistas."""
        from app.domain.rag_service import RAGService

        mock_service = MagicMock(spec=RAGService)
        mock_service.public_retrieval_enabled = True
        mock_service.chat.return_value = ChatResponse(
            answer=(
                "Com base nos documentos do projeto e no acervo publico, "
                "a abordagem construtivista e amplamente discutida."
            ),
            sources=[
                Source(
                    document="project-thesis.pdf",
                    page=22,
                    section="Revisao Bibliografica",
                    score=0.93,
                    source_type="project_document",
                ),
                Source(
                    document="pedagogy-foundations.pdf",
                    page=42,
                    section="Construtivismo",
                    score=0.88,
                    source_type="public_library",
                ),
            ],
            session_id=session_id,
        )
        mock_rag_cls.return_value = mock_service

        payload = {
            "project_id": project_id,
            "session_id": session_id,
            "message": "Compare as abordagens construtivistas",
            "retrieval_mode": "project_plus_public",
        }
        res = client.post("/api/v1/chat", json=payload)

        assert res.status_code == 200
        data = res.json()

        # Verificar resposta com fontes mistas
        assert data["answer"] != ""
        assert len(data["sources"]) == 2

        # Verificar que ha fonte do projeto e fonte publica
        documents = [s["document"] for s in data["sources"]]
        assert "project-thesis.pdf" in documents
        assert "pedagogy-foundations.pdf" in documents

        # Verificar source_type correto para cada fonte
        source_types = {s["document"]: s["source_type"] for s in data["sources"]}
        assert source_types["project-thesis.pdf"] == "project_document"
        assert source_types["pedagogy-foundations.pdf"] == "public_library"

    @patch("app.api.v1.endpoints.chat.RAGService")
    def test_project_plus_public_fallback_to_project_only(
        self,
        mock_rag_cls,
        client: TestClient,
        project_id: str,
        session_id: str,
    ) -> None:
        """Se acervo publico vazio, retorna apenas fontes do projeto."""
        from app.domain.rag_service import RAGService

        mock_service = MagicMock(spec=RAGService)
        mock_service.public_retrieval_enabled = True
        mock_service.chat.return_value = ChatResponse(
            answer="Com base nos documentos do projeto disponiveis.",
            sources=[
                Source(
                    document="project-doc.pdf",
                    page=5,
                    score=0.91,
                ),
            ],
            session_id=session_id,
        )
        mock_rag_cls.return_value = mock_service

        payload = {
            "project_id": project_id,
            "session_id": session_id,
            "message": "Pergunta especifica do projeto",
            "retrieval_mode": "project_plus_public",
        }
        res = client.post("/api/v1/chat", json=payload)

        assert res.status_code == 200
        data = res.json()
        assert len(data["sources"]) >= 1


# ---------------------------------------------------------------------------
# E2E Smoke: Document Processing Flow
# ---------------------------------------------------------------------------


class TestE2EDocumentProcessing:
    """Testes e2e do fluxo de processamento de documento."""

    @patch("app.api.v1.endpoints.documents.PgVectorStore")
    @patch("app.api.v1.endpoints.documents.OpenAIEmbedder")
    def test_process_document_success(
        self,
        mock_embedder_cls,
        mock_store_cls,
        client: TestClient,
        project_id: str,
        document_id: str,
    ) -> None:
        """Processamento de documento retorna status success."""
        # Configurar mocks
        mock_embedder = MagicMock()
        mock_embedder.embed_text.return_value = [0.1] * 1536
        mock_embedder._use_mock = True
        mock_embedder_cls.return_value = mock_embedder

        mock_store = MagicMock()
        mock_store.store_chunks.return_value = 10
        mock_store_cls.return_value = mock_store

        payload = {
            "project_id": project_id,
            "document_id": document_id,
            "storage_key": "s3://bucket/test-doc.pdf",
            "source_type": "user_upload",
        }
        res = client.post("/api/v1/documents/process", json=payload)

        # Pode ser 200 (sincrono) ou 202 (assincrono via Go gateway)
        assert res.status_code in (200, 202)

    @patch("app.api.v1.endpoints.documents.PgVectorStore")
    @patch("app.api.v1.endpoints.documents.OpenAIEmbedder")
    def test_process_document_invalid_storage_key(
        self,
        mock_embedder_cls,
        mock_store_cls,
        client: TestClient,
        project_id: str,
        document_id: str,
    ) -> None:
        """Storage key invalido deve ser rejeitado."""
        mock_embedder = MagicMock()
        mock_embedder._use_mock = True
        mock_embedder_cls.return_value = mock_embedder

        mock_store = MagicMock()
        mock_store_cls.return_value = mock_store

        payload = {
            "project_id": project_id,
            "document_id": document_id,
            "storage_key": "",  # Invalido
            "source_type": "user_upload",
        }
        res = client.post("/api/v1/documents/process", json=payload)

        # Pode ser validacao Pydantic ou logica de negocio
        assert res.status_code in (400, 422)


# ---------------------------------------------------------------------------
# E2E Smoke: Contract Validation
# ---------------------------------------------------------------------------


class TestE2EContractValidation:
    """Validacao de contratos entre Go gateway e Python agent."""

    def test_chat_request_accepts_retrieval_mode(self) -> None:
        """ChatRequest aceita campo retrieval_mode."""
        from app.schemas.contracts_v1 import ChatRequest

        req = ChatRequest(
            project_id=uuid.uuid4(),
            session_id="test-session",
            message="Test question",
            retrieval_mode="project_plus_public",
        )

        assert req.retrieval_mode == "project_plus_public"

        # Serializacao JSON deve incluir retrieval_mode
        data = req.model_dump(mode="json")
        assert "retrieval_mode" in data
        assert data["retrieval_mode"] == "project_plus_public"

    def test_chat_request_default_retrieval_mode(self) -> None:
        """ChatRequest usa project_only como padrao."""
        from app.schemas.contracts_v1 import ChatRequest

        req = ChatRequest(
            project_id=uuid.uuid4(),
            session_id="test-session",
            message="Test question",
        )

        assert req.retrieval_mode == "project_only"

    def test_chat_response_serialization(self) -> None:
        """ChatResponse serializa corretamente para JSON."""
        from app.schemas.contracts_v1 import ChatResponse, Source

        resp = ChatResponse(
            answer="Test answer",
            sources=[
                Source(document="doc.pdf", page=1, score=0.9),
            ],
            session_id="test-session",
        )

        data = resp.model_dump(mode="json")
        assert data["answer"] == "Test answer"
        assert len(data["sources"]) == 1
        assert data["sources"][0]["document"] == "doc.pdf"
        assert data["sources"][0]["page"] == 1
        assert data["sources"][0]["score"] == 0.9
        assert data["session_id"] == "test-session"

    def test_chat_response_json_roundtrip(self) -> None:
        """ChatResponse pode ser serializado e desserializado."""
        from app.schemas.contracts_v1 import ChatResponse, Source

        original = ChatResponse(
            answer="Roundtrip test",
            sources=[
                Source(document="a.pdf", page=1, section="Intro", score=0.95),
                Source(document="b.pdf", page=42, score=0.88),
            ],
            session_id="roundtrip-session",
        )

        json_str = original.model_dump_json()
        restored = ChatResponse.model_validate_json(json_str)

        assert restored.answer == original.answer
        assert len(restored.sources) == len(original.sources)
        assert restored.session_id == original.session_id


# ---------------------------------------------------------------------------
# E2E Smoke: Error Handling
# ---------------------------------------------------------------------------


class TestE2EErrorHandling:
    """Testes e2e de tratamento de erro."""

    @patch("app.api.v1.endpoints.chat.RAGService")
    def test_llm_error_returns_502(
        self,
        mock_rag_cls,
        client: TestClient,
        project_id: str,
        session_id: str,
    ) -> None:
        """Erro do LLM retorna 502 Bad Gateway."""
        from app.domain.rag_service import LLMError, RAGService

        mock_service = MagicMock(spec=RAGService)
        mock_service.chat.side_effect = LLMError("OpenAI API error")
        mock_rag_cls.return_value = mock_service

        payload = {
            "project_id": project_id,
            "session_id": session_id,
            "message": "Pergunta que causa erro",
        }
        res = client.post("/api/v1/chat", json=payload)

        assert res.status_code == 502

    def test_invalid_project_id_returns_422(
        self,
        client: TestClient,
    ) -> None:
        """project_id invalido retorna 422."""
        payload = {
            "project_id": "not-a-uuid",
            "session_id": "sess",
            "message": "Test",
        }
        res = client.post("/api/v1/chat", json=payload)

        assert res.status_code == 422

    def test_missing_required_fields_returns_422(
        self,
        client: TestClient,
    ) -> None:
        """Campos obrigatorios ausentes retornam 422."""
        payload = {
            "session_id": "sess",
            # project_id ausente
        }
        res = client.post("/api/v1/chat", json=payload)

        assert res.status_code == 422
