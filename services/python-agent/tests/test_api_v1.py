"""
Testes da API v1.

Verifica health endpoints e stubs de cada operacao com payload valido.
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


# ---------------------------------------------------------------------------
# Health endpoints
# ---------------------------------------------------------------------------


class TestHealthEndpoints:
    """Testes de health check e readiness."""

    def test_health_returns_ok(self, client: TestClient) -> None:
        res = client.get("/api/v1/health")
        assert res.status_code == 200
        assert res.json() == {"status": "ok"}

    def test_ready_returns_ready(self, client: TestClient) -> None:
        res = client.get("/api/v1/ready")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ready"
        assert data["checks"]["database"] == "ok"


# ---------------------------------------------------------------------------
# Documents endpoint
# ---------------------------------------------------------------------------


class TestDocumentsEndpoint:
    """Testes de processamento de documentos."""

    @patch("app.api.v1.endpoints.documents.update_document_status")
    @patch("app.api.v1.endpoints.documents.PgVectorStore")
    @patch("app.api.v1.endpoints.documents.OpenAIEmbedder")
    @patch("app.api.v1.endpoints.documents.TextChunker")
    @patch("app.api.v1.endpoints.documents.PDFExtractor")
    @patch("app.api.v1.endpoints.documents.MinIOClient")
    def test_process_document_returns_ready(
        self,
        mock_minio_cls,
        mock_extractor_cls,
        mock_chunker_cls,
        mock_embedder_cls,
        mock_store_cls,
        mock_update_status,
        client: TestClient,
    ) -> None:
        """Verifica pipeline completo retorna status ready."""
        # Configura mocks minimos
        mock_minio = MagicMock()
        mock_minio.download_file.return_value = b"%PDF-1.4 fake"
        mock_minio_cls.return_value = mock_minio

        mock_extractor = MagicMock()
        mock_extractor.extract_text.return_value = [
            {"page_number": 1, "text": "Test content"}
        ]
        mock_extractor_cls.return_value = mock_extractor

        mock_chunker = MagicMock()
        mock_chunker.chunk_pages.return_value = [
            {"text": "chunk", "page_number": 1, "chunk_index": 0}
        ]
        mock_chunker_cls.return_value = mock_chunker

        mock_embedder = MagicMock()
        mock_embedder.embed_texts.return_value = [[0.1] * 1536]
        mock_embedder_cls.return_value = mock_embedder

        mock_store = MagicMock()
        mock_store.insert_embeddings.return_value = 1
        mock_store_cls.return_value = mock_store

        mock_update_status.return_value = None

        payload = {
            "project_id": str(uuid4()),
            "document_id": str(uuid4()),
            "storage_key": "test-bucket/doc.pdf",
            "source_type": "user_upload",
        }
        res = client.post("/api/v1/documents/process-document", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ready"
        assert "document_id" in data
        assert data["chunks_count"] == 1


# ---------------------------------------------------------------------------
# Chat endpoint
# ---------------------------------------------------------------------------


class TestChatEndpoint:
    """Testes de chat RAG."""

    @patch("app.api.v1.endpoints.chat.RAGService")
    def test_chat_returns_answer(self, mock_rag_cls, client: TestClient) -> None:
        """Verifica chat retorna resposta com sources."""
        from app.schemas.contracts_v1 import ChatResponse

        mock_service = MagicMock()
        mock_service.chat.return_value = ChatResponse(
            answer="Resposta baseada no contexto dos documentos.",
            sources=[],
            session_id="test-session-1",
        )
        mock_rag_cls.return_value = mock_service

        payload = {
            "project_id": str(uuid4()),
            "session_id": "test-session-1",
            "message": "Qual o objetivo deste documento?",
        }
        res = client.post("/api/v1/chat", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert "answer" in data
        assert data["session_id"] == "test-session-1"


# ---------------------------------------------------------------------------
# Summarize endpoint
# ---------------------------------------------------------------------------


class TestSummarizeEndpoint:
    """Testes de resumo de documentos."""

    @patch("app.api.v1.endpoints.summarize.SummarizeService")
    def test_summarize_returns_structured_summary(
        self, mock_service_cls, client: TestClient
    ) -> None:
        """Verifica resumo estruturado com SummarizeService mockado."""
        from app.schemas.contracts_v1 import SummarizeResponse

        doc_id = uuid4()
        mock_service = MagicMock()
        mock_service.summarize.return_value = SummarizeResponse(
            document_id=doc_id,
            summary={
                "objective": "Objetivo real do documento.",
                "methodology": "Metodologia aplicada.",
                "results": "Resultados obtidos.",
                "conclusion": "Conclusao do trabalho.",
            },
        )
        mock_service_cls.return_value = mock_service

        payload = {
            "document_id": str(doc_id),
            "project_id": str(uuid4()),
            "format": "structured",
        }
        res = client.post("/api/v1/summarize/summarize-document", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert "summary" in data
        summary = data["summary"]
        assert "objective" in summary
        assert "methodology" in summary
        assert "results" in summary
        assert "conclusion" in summary
        assert summary["objective"] == "Objetivo real do documento."

    @patch("app.api.v1.endpoints.summarize.SummarizeService")
    def test_summarize_returns_insufficient_context(
        self, mock_service_cls, client: TestClient
    ) -> None:
        """Verifica fallback quando documento nao tem chunks."""
        from app.schemas.contracts_v1 import SummarizeResponse

        doc_id = uuid4()
        mock_service = MagicMock()
        mock_service.summarize.return_value = SummarizeResponse(
            document_id=doc_id,
            summary={
                "objective": "Contexto insuficiente para gerar resumo.",
                "methodology": "Contexto insuficiente para gerar resumo.",
                "results": "Contexto insuficiente para gerar resumo.",
                "conclusion": "Contexto insuficiente para gerar resumo.",
            },
        )
        mock_service_cls.return_value = mock_service

        payload = {
            "document_id": str(doc_id),
            "project_id": str(uuid4()),
            "format": "structured",
        }
        res = client.post("/api/v1/summarize/summarize-document", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert (
            data["summary"]["objective"] == "Contexto insuficiente para gerar resumo."
        )


# ---------------------------------------------------------------------------
# Compare endpoint
# ---------------------------------------------------------------------------


class TestCompareEndpoint:
    """Testes de comparacao de documentos."""

    @patch("app.api.v1.endpoints.compare.CompareService")
    def test_compare_returns_comparison(
        self, mock_service_cls, client: TestClient
    ) -> None:
        """Verifica comparacao tematica com CompareService mockado."""
        from app.schemas.contracts_v1 import CompareResponse, Source

        project_id = uuid4()
        doc_a = str(uuid4())
        doc_b = str(uuid4())

        mock_service = MagicMock()
        mock_service.compare.return_value = CompareResponse(
            project_id=project_id,
            comparison={
                "theme": "metodologia de pesquisa",
                "similarities": "Ambos utilizam abordagem qualitativa.",
                "differences": "Doc A usa entrevistas, Doc B usa survey.",
                "synthesis": "Documentos complementares sobre metodologia.",
            },
            sources=[
                Source(document=doc_a, page=1, score=0.92),
                Source(document=doc_b, page=2, score=0.85),
            ],
        )
        mock_service_cls.return_value = mock_service

        payload = {
            "project_id": str(project_id),
            "document_ids": [doc_a, doc_b],
            "theme": "metodologia de pesquisa",
        }
        res = client.post("/api/v1/compare/compare-documents", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert "comparison" in data
        assert data["comparison"]["theme"] == "metodologia de pesquisa"
        assert "similarities" in data["comparison"]
        assert "differences" in data["comparison"]
        assert "synthesis" in data["comparison"]
        assert len(data["sources"]) == 2
        assert data["sources"][0]["document"] == doc_a
        assert data["sources"][0]["score"] == 0.92

    @patch("app.api.v1.endpoints.compare.CompareService")
    def test_compare_returns_insufficient_context(
        self, mock_service_cls, client: TestClient
    ) -> None:
        """Verifica fallback quando documentos nao tem chunks suficientes."""
        from app.schemas.contracts_v1 import CompareResponse

        project_id = uuid4()
        doc_a = str(uuid4())
        doc_b = str(uuid4())

        mock_service = MagicMock()
        mock_service.compare.return_value = CompareResponse(
            project_id=project_id,
            comparison={
                "theme": "tema inexistente",
                "similarities": "Contexto insuficiente para comparacao tematica.",
                "differences": "Contexto insuficiente para comparacao tematica.",
                "synthesis": "Contexto insuficiente para comparacao tematica.",
            },
            sources=[],
        )
        mock_service_cls.return_value = mock_service

        payload = {
            "project_id": str(project_id),
            "document_ids": [doc_a, doc_b],
            "theme": "tema inexistente",
        }
        res = client.post("/api/v1/compare/compare-documents", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert (
            data["comparison"]["similarities"]
            == "Contexto insuficiente para comparacao tematica."
        )
        assert data["sources"] == []


# ---------------------------------------------------------------------------
# Research Gaps endpoint
# ---------------------------------------------------------------------------


class TestResearchGapsEndpoint:
    """Testes de identificacao de lacunas de pesquisa."""

    @patch("app.api.v1.endpoints.research.ResearchGapService")
    def test_research_gaps_returns_list(
        self, mock_service_cls, client: TestClient
    ) -> None:
        """Verifica que endpoint retorna lista de lacunas."""
        from app.schemas.contracts_v1 import (
            ResearchGapItem,
            ResearchGapResponse,
            Source,
        )

        project_id = uuid4()

        mock_service = MagicMock()
        mock_service.find_gaps.return_value = ResearchGapResponse(
            project_id=project_id,
            gaps=[
                ResearchGapItem(
                    gap_title="Lacuna sobre metodologias ativas",
                    why_gap="Falta evidencia sobre eficacia de abordagens ativas.",
                    evidence_sources=[
                        Source(document="doc1.pdf", page=1, score=0.92),
                    ],
                    suggested_questions=[
                        "Como metodologias ativas afetam o engajamento?",
                    ],
                    confidence="high",
                ),
            ],
        )
        mock_service_cls.return_value = mock_service

        payload = {
            "project_id": str(project_id),
            "theme": "metodologias ativas",
        }
        res = client.post("/api/v1/research/gaps", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert "gaps" in data
        assert len(data["gaps"]) == 1
        assert data["gaps"][0]["gap_title"] == "Lacuna sobre metodologias ativas"
        assert data["gaps"][0]["confidence"] == "high"
        assert len(data["gaps"][0]["evidence_sources"]) == 1

    @patch("app.api.v1.endpoints.research.ResearchGapService")
    def test_research_gaps_empty_corpus(
        self, mock_service_cls, client: TestClient
    ) -> None:
        """Verifica que retorna lista vazia quando corpus vazio."""
        from app.schemas.contracts_v1 import ResearchGapResponse

        project_id = uuid4()

        mock_service = MagicMock()
        mock_service.find_gaps.return_value = ResearchGapResponse(
            project_id=project_id,
            gaps=[],
        )
        mock_service_cls.return_value = mock_service

        payload = {
            "project_id": str(project_id),
            "theme": "",
        }
        res = client.post("/api/v1/research/gaps", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["gaps"] == []
