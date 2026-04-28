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

    def test_chat_returns_answer(self, client: TestClient) -> None:
        payload = {
            "project_id": str(uuid4()),
            "session_id": "test-session-1",
            "message": "Qual o objetivo deste documento?",
        }
        res = client.post("/api/v1/chat", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert "answer" in data
        assert data["sources"] == []
        assert data["session_id"] == "test-session-1"


# ---------------------------------------------------------------------------
# Summarize endpoint
# ---------------------------------------------------------------------------


class TestSummarizeEndpoint:
    """Testes de resumo de documentos."""

    def test_summarize_returns_structured_summary(self, client: TestClient) -> None:
        payload = {
            "document_id": str(uuid4()),
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


# ---------------------------------------------------------------------------
# Compare endpoint
# ---------------------------------------------------------------------------


class TestCompareEndpoint:
    """Testes de comparacao de documentos."""

    def test_compare_returns_comparison(self, client: TestClient) -> None:
        doc_a = str(uuid4())
        doc_b = str(uuid4())
        payload = {
            "project_id": str(uuid4()),
            "document_ids": [doc_a, doc_b],
            "theme": "metodologia de pesquisa",
        }
        res = client.post("/api/v1/compare/compare-documents", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert "comparison" in data
        assert data["sources"] == []
        assert data["comparison"]["theme"] == "metodologia de pesquisa"
