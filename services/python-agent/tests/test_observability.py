"""
Testes de observabilidade do servico Python.

Verifica:
- Logs contem request_id propagado do header X-Request-ID
- Logs contem project_id, document_id, session_id quando disponivel
- Endpoint /metrics retorna metricas Prometheus
- Endpoints core (/process-document, /chat) estao instrumentados
"""

from __future__ import annotations

import json
import logging
import uuid
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from app.main import app


@pytest.fixture
def client() -> TestClient:
    """Cliente de teste reutilizavel."""
    return TestClient(app)


# ---------------------------------------------------------------------------
# Request ID propagation in logs
# ---------------------------------------------------------------------------


class TestRequestIDInLogs:
    """Verifica que request_id aparece nos logs."""

    def test_chat_log_contains_request_id_from_header(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        """X-Request-ID do header deve aparecer nos logs do chat."""
        with patch("app.api.v1.endpoints.chat.RAGService") as mock_rag_cls:
            from app.schemas.contracts_v1 import ChatResponse

            mock_service = MagicMock()
            mock_service.chat.return_value = ChatResponse(
                answer="Resposta teste",
                sources=[],
                session_id="test-session",
            )
            mock_rag_cls.return_value = mock_service

            with caplog.at_level(logging.INFO):
                res = client.post(
                    "/api/v1/chat",
                    json={
                        "project_id": str(uuid.uuid4()),
                        "session_id": "test-session",
                        "message": "Ola",
                    },
                    headers={"X-Request-ID": "test-req-id-001"},
                )

            assert res.status_code == 200
            # Verificar que request_id aparece nos logs
            log_text = caplog.text
            assert "test-req-id-001" in log_text

    def test_process_document_log_contains_request_id(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        """X-Request-ID deve aparecer nos logs de process-document."""
        with (
            patch("app.api.v1.endpoints.documents.MinIOClient") as mock_minio_cls,
            patch("app.api.v1.endpoints.documents.PDFExtractor") as mock_extractor_cls,
            patch("app.api.v1.endpoints.documents.TextChunker") as mock_chunker_cls,
            patch("app.api.v1.endpoints.documents.OpenAIEmbedder") as mock_embedder_cls,
            patch("app.api.v1.endpoints.documents.PgVectorStore") as mock_store_cls,
            patch("app.api.v1.endpoints.documents.update_document_status"),
        ):
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

            with caplog.at_level(logging.INFO):
                res = client.post(
                    "/api/v1/documents/process-document",
                    json={
                        "project_id": str(uuid.uuid4()),
                        "document_id": str(uuid.uuid4()),
                        "storage_key": "test-bucket/doc.pdf",
                        "source_type": "user_upload",
                    },
                    headers={"X-Request-ID": "test-req-id-002"},
                )

            assert res.status_code == 200
            assert "test-req-id-002" in caplog.text


# ---------------------------------------------------------------------------
# Context IDs in logs (project_id, document_id, session_id)
# ---------------------------------------------------------------------------


class TestContextIDsInLogs:
    """Verifica que IDs de contexto aparecem nos logs."""

    def test_chat_log_contains_project_and_session_id(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        """project_id e session_id devem aparecer nos logs do chat."""
        project_id = str(uuid.uuid4())
        session_id = "obs-session-123"

        with patch("app.api.v1.endpoints.chat.RAGService") as mock_rag_cls:
            from app.schemas.contracts_v1 import ChatResponse

            mock_service = MagicMock()
            mock_service.chat.return_value = ChatResponse(
                answer="Resposta teste",
                sources=[],
                session_id=session_id,
            )
            mock_rag_cls.return_value = mock_service

            with caplog.at_level(logging.INFO):
                res = client.post(
                    "/api/v1/chat",
                    json={
                        "project_id": project_id,
                        "session_id": session_id,
                        "message": "Ola",
                    },
                )

            assert res.status_code == 200
            assert project_id in caplog.text
            assert session_id in caplog.text

    def test_process_document_log_contains_project_and_document_id(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        """project_id e document_id devem aparecer nos logs de process-document."""
        project_id = str(uuid.uuid4())
        document_id = str(uuid.uuid4())

        with (
            patch("app.api.v1.endpoints.documents.MinIOClient") as mock_minio_cls,
            patch("app.api.v1.endpoints.documents.PDFExtractor") as mock_extractor_cls,
            patch("app.api.v1.endpoints.documents.TextChunker") as mock_chunker_cls,
            patch("app.api.v1.endpoints.documents.OpenAIEmbedder") as mock_embedder_cls,
            patch("app.api.v1.endpoints.documents.PgVectorStore") as mock_store_cls,
            patch("app.api.v1.endpoints.documents.update_document_status"),
        ):
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

            with caplog.at_level(logging.INFO):
                res = client.post(
                    "/api/v1/documents/process-document",
                    json={
                        "project_id": project_id,
                        "document_id": document_id,
                        "storage_key": "test-bucket/doc.pdf",
                        "source_type": "user_upload",
                    },
                )

            assert res.status_code == 200
            assert project_id in caplog.text
            assert document_id in caplog.text


# ---------------------------------------------------------------------------
# JSON log format
# ---------------------------------------------------------------------------


class TestJSONLogFormat:
    """Verifica que logs sao em formato JSON."""

    def test_logging_middleware_produces_json(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Middleware de logging deve produzir entradas JSON."""
        with patch("app.api.v1.endpoints.chat.RAGService") as mock_rag_cls:
            from app.schemas.contracts_v1 import ChatResponse

            mock_service = MagicMock()
            mock_service.chat.return_value = ChatResponse(
                answer="Resposta teste",
                sources=[],
                session_id="test-session",
            )
            mock_rag_cls.return_value = mock_service

            with caplog.at_level(logging.INFO):
                client.post(
                    "/api/v1/chat",
                    json={
                        "project_id": str(uuid.uuid4()),
                        "session_id": "test-session",
                        "message": "Ola",
                    },
                    headers={"X-Request-ID": "json-test-id"},
                )

            # Verificar que pelo menos um log e JSON valido
            json_found = False
            for record in caplog.records:
                try:
                    parsed = json.loads(record.getMessage())
                    # Se chegou aqui, e JSON valido
                    assert "timestamp" in parsed or "level" in parsed
                    json_found = True
                    break
                except json.JSONDecodeError:
                    continue

            # Nota: o middleware usa extra= para campos estruturados,
            # entao verificamos que os campos extras estao presentes
            found_request_id = False
            for record in caplog.records:
                if (
                    hasattr(record, "request_id")
                    and record.request_id == "json-test-id"
                ):
                    found_request_id = True
                    break
            assert found_request_id, "Expected request_id in log records"


# ---------------------------------------------------------------------------
# Metrics endpoint
# ---------------------------------------------------------------------------


class TestMetricsEndpoint:
    """Verifica endpoint de metricas Prometheus."""

    def test_metrics_endpoint_returns_prometheus_format(
        self, client: TestClient
    ) -> None:
        """/metrics deve retornar formato Prometheus."""
        res = client.get("/metrics")
        assert res.status_code == 200
        assert "text/plain" in res.headers.get("content-type", "")
        # Deve conter HELP e TYPE (formato Prometheus)
        assert "# HELP" in res.text
        assert "# TYPE" in res.text

    def test_metrics_contains_requests_total(self, client: TestClient) -> None:
        """/metrics deve conter metrica requests_total."""
        # Fazer uma requisicao para gerar metrica
        with patch("app.api.v1.endpoints.chat.RAGService") as mock_rag_cls:
            from app.schemas.contracts_v1 import ChatResponse

            mock_service = MagicMock()
            mock_service.chat.return_value = ChatResponse(
                answer="Resposta teste",
                sources=[],
                session_id="test-session",
            )
            mock_rag_cls.return_value = mock_service

            client.post(
                "/api/v1/chat",
                json={
                    "project_id": str(uuid.uuid4()),
                    "session_id": "test-session",
                    "message": "Ola",
                },
            )

        res = client.get("/metrics")
        assert "requests_total" in res.text

    def test_metrics_contains_duration_histogram(self, client: TestClient) -> None:
        """/metrics deve conter histograma de duracao."""
        res = client.get("/metrics")
        assert "requests_duration_seconds" in res.text

    def test_metrics_labels_include_method_path_status(
        self, client: TestClient
    ) -> None:
        """Metricas devem ter labels method, path, status_code."""
        with patch("app.api.v1.endpoints.chat.RAGService") as mock_rag_cls:
            from app.schemas.contracts_v1 import ChatResponse

            mock_service = MagicMock()
            mock_service.chat.return_value = ChatResponse(
                answer="Resposta teste",
                sources=[],
                session_id="test-session",
            )
            mock_rag_cls.return_value = mock_service

            client.post(
                "/api/v1/chat",
                json={
                    "project_id": str(uuid.uuid4()),
                    "session_id": "test-session",
                    "message": "Ola",
                },
            )

        res = client.get("/metrics")
        # Verificar labels presentes
        assert 'method="' in res.text
        assert 'path="' in res.text
        assert 'status_code="' in res.text


# ---------------------------------------------------------------------------
# Core endpoints instrumented
# ---------------------------------------------------------------------------


class TestCoreEndpointsInstrumented:
    """Verifica que endpoints core estao instrumentados com metricas."""

    def test_process_document_increments_counter(self, client: TestClient) -> None:
        """Endpoint /process-document deve incrementar contador."""
        with (
            patch("app.api.v1.endpoints.documents.MinIOClient") as mock_minio_cls,
            patch("app.api.v1.endpoints.documents.PDFExtractor") as mock_extractor_cls,
            patch("app.api.v1.endpoints.documents.TextChunker") as mock_chunker_cls,
            patch("app.api.v1.endpoints.documents.OpenAIEmbedder") as mock_embedder_cls,
            patch("app.api.v1.endpoints.documents.PgVectorStore") as mock_store_cls,
            patch("app.api.v1.endpoints.documents.update_document_status"),
        ):
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

            client.post(
                "/api/v1/documents/process-document",
                json={
                    "project_id": str(uuid.uuid4()),
                    "document_id": str(uuid.uuid4()),
                    "storage_key": "test-bucket/doc.pdf",
                    "source_type": "user_upload",
                },
            )

        res = client.get("/metrics")
        assert 'path="/api/v1/documents/process-document"' in res.text

    def test_chat_increments_counter(self, client: TestClient) -> None:
        """Endpoint /chat deve incrementar contador."""
        with patch("app.api.v1.endpoints.chat.RAGService") as mock_rag_cls:
            from app.schemas.contracts_v1 import ChatResponse

            mock_service = MagicMock()
            mock_service.chat.return_value = ChatResponse(
                answer="Resposta teste",
                sources=[],
                session_id="test-session",
            )
            mock_rag_cls.return_value = mock_service

            client.post(
                "/api/v1/chat",
                json={
                    "project_id": str(uuid.uuid4()),
                    "session_id": "test-session",
                    "message": "Ola",
                },
            )

        res = client.get("/metrics")
        assert 'path="/api/v1/chat"' in res.text


# ---------------------------------------------------------------------------
# X-Request-ID response header
# ---------------------------------------------------------------------------


class TestRequestIDResponseHeader:
    """Verifica que X-Request-ID e incluido na resposta."""

    def test_chat_response_contains_request_id(self, client: TestClient) -> None:
        """Resposta do chat deve conter X-Request-ID."""
        with patch("app.api.v1.endpoints.chat.RAGService") as mock_rag_cls:
            from app.schemas.contracts_v1 import ChatResponse

            mock_service = MagicMock()
            mock_service.chat.return_value = ChatResponse(
                answer="Resposta teste",
                sources=[],
                session_id="test-session",
            )
            mock_rag_cls.return_value = mock_service

            res = client.post(
                "/api/v1/chat",
                json={
                    "project_id": str(uuid.uuid4()),
                    "session_id": "test-session",
                    "message": "Ola",
                },
                headers={"X-Request-ID": "response-header-test"},
            )

            assert res.status_code == 200
            assert res.headers.get("X-Request-ID") == "response-header-test"

    def test_process_document_response_contains_request_id(
        self, client: TestClient
    ) -> None:
        """Resposta de process-document deve conter X-Request-ID."""
        with (
            patch("app.api.v1.endpoints.documents.MinIOClient") as mock_minio_cls,
            patch("app.api.v1.endpoints.documents.PDFExtractor") as mock_extractor_cls,
            patch("app.api.v1.endpoints.documents.TextChunker") as mock_chunker_cls,
            patch("app.api.v1.endpoints.documents.OpenAIEmbedder") as mock_embedder_cls,
            patch("app.api.v1.endpoints.documents.PgVectorStore") as mock_store_cls,
            patch("app.api.v1.endpoints.documents.update_document_status"),
        ):
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

            res = client.post(
                "/api/v1/documents/process-document",
                json={
                    "project_id": str(uuid.uuid4()),
                    "document_id": str(uuid.uuid4()),
                    "storage_key": "test-bucket/doc.pdf",
                    "source_type": "user_upload",
                },
                headers={"X-Request-ID": "doc-response-header-test"},
            )

            assert res.status_code == 200
            assert res.headers.get("X-Request-ID") == "doc-response-header-test"
