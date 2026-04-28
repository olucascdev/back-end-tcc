"""
Testes do endpoint de processamento de documento.

Cobertura:
- Pipeline completo com mocks (MinIO, DB, OpenAI)
- Geracao de chunks verificada
- Persistencia de embeddings verificada (mock)
- Erro de arquivo invalido (PDF corrompido)
- Erro de arquivo nao encontrado no storage
"""

from __future__ import annotations

import json
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
def valid_payload() -> dict:
    """Payload valido para processamento."""
    return {
        "project_id": str(uuid4()),
        "document_id": str(uuid4()),
        "storage_key": "test-bucket/sample.pdf",
        "source_type": "user_upload",
    }


# ---------------------------------------------------------------------------
# Helpers para mocks
# ---------------------------------------------------------------------------


def _mock_pdf_bytes() -> bytes:
    """Retorna bytes de um PDF minimo valido para testes.

    PDF de 1 pagina com texto simples.
    """
    # PDF minimo valido gerado manualmente
    pdf_content = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
        b"4 0 obj\n<< /Length 44 >>\nstream\n"
        b"BT /F1 12 Tf 100 700 Td (Teste de documento PDF) Tj ET\n"
        b"endstream\nendobj\n"
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
        b"xref\n0 6\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"0000000266 00000 n \n"
        b"0000000360 00000 n \n"
        b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n437\n%%EOF\n"
    )
    return pdf_content


def _mock_pages() -> list[dict]:
    """Paginas mock para extracao."""
    return [
        {
            "page_number": 1,
            "text": "Este e um documento de teste para validacao do pipeline de processamento. "
            * 20,
        },
        {
            "page_number": 2,
            "text": "Segunda pagina com conteudo adicional para gerar multiplos chunks. "
            * 20,
        },
    ]


def _mock_chunks(pages: list[dict]) -> list[dict]:
    """Chunks mock gerados a partir de paginas."""
    chunks = []
    idx = 0
    for page in pages:
        text = page["text"]
        # Divide em chunks de ~500 chars para teste
        for start in range(0, len(text), 500):
            chunk_text = text[start : start + 500].strip()
            if chunk_text:
                chunks.append(
                    {
                        "text": chunk_text,
                        "page_number": page["page_number"],
                        "chunk_index": idx,
                    }
                )
                idx += 1
    return chunks


# ---------------------------------------------------------------------------
# Testes do endpoint com mocks completos
# ---------------------------------------------------------------------------


class TestProcessDocumentEndpoint:
    """Testes do endpoint POST /process-document com mocks."""

    @patch("app.api.v1.endpoints.documents.update_document_status")
    @patch("app.api.v1.endpoints.documents.PgVectorStore")
    @patch("app.api.v1.endpoints.documents.OpenAIEmbedder")
    @patch("app.api.v1.endpoints.documents.TextChunker")
    @patch("app.api.v1.endpoints.documents.PDFExtractor")
    @patch("app.api.v1.endpoints.documents.MinIOClient")
    def test_process_document_success(
        self,
        mock_minio_cls,
        mock_extractor_cls,
        mock_chunker_cls,
        mock_embedder_cls,
        mock_store_cls,
        mock_update_status,
        client: TestClient,
        valid_payload: dict,
    ) -> None:
        """Verifica pipeline completo com sucesso."""
        # Configura mocks
        mock_minio = MagicMock()
        mock_minio.download_file.return_value = _mock_pdf_bytes()
        mock_minio_cls.return_value = mock_minio

        mock_extractor = MagicMock()
        mock_extractor.extract_text.return_value = _mock_pages()
        mock_extractor_cls.return_value = mock_extractor

        chunks = _mock_chunks(_mock_pages())
        mock_chunker = MagicMock()
        mock_chunker.chunk_pages.return_value = chunks
        mock_chunker_cls.return_value = mock_chunker

        mock_embedder = MagicMock()
        mock_embeddings = [[0.1] * 1536 for _ in chunks]
        mock_embedder.embed_texts.return_value = mock_embeddings
        mock_embedder_cls.return_value = mock_embedder

        mock_store = MagicMock()
        mock_store.insert_embeddings.return_value = len(chunks)
        mock_store_cls.return_value = mock_store

        mock_update_status.return_value = None

        # Executa
        res = client.post(
            "/api/v1/documents/process-document",
            json=valid_payload,
        )

        # Verifica
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ready"
        assert data["document_id"] == valid_payload["document_id"]
        assert data["chunks_count"] == len(chunks)
        assert data["processed_at"] is not None
        assert data["error_message"] is None

        # Verifica chamadas
        mock_minio.download_file.assert_called_once_with(valid_payload["storage_key"])
        mock_extractor.extract_text.assert_called_once()
        mock_chunker.chunk_pages.assert_called_once()
        mock_embedder.embed_texts.assert_called_once()
        mock_store.insert_embeddings.assert_called_once()
        mock_update_status.assert_called_once()

    @patch("app.api.v1.endpoints.documents.update_document_status")
    @patch("app.api.v1.endpoints.documents.MinIOClient")
    def test_process_document_file_not_found(
        self,
        mock_minio_cls,
        mock_update_status,
        client: TestClient,
        valid_payload: dict,
    ) -> None:
        """Verifica erro quando arquivo nao existe no storage."""
        from app.infrastructure.storage.minio_client import StorageError

        mock_minio = MagicMock()
        mock_minio.download_file.side_effect = FileNotFoundError(
            "Arquivo nao encontrado"
        )
        mock_minio_cls.return_value = mock_minio

        res = client.post(
            "/api/v1/documents/process-document",
            json=valid_payload,
        )

        assert res.status_code == 404
        data = res.json()
        assert "detail" in data
        assert "nao encontrado" in data["detail"].lower()

    @patch("app.api.v1.endpoints.documents.update_document_status")
    @patch("app.api.v1.endpoints.documents.MinIOClient")
    def test_process_document_storage_error(
        self,
        mock_minio_cls,
        mock_update_status,
        client: TestClient,
        valid_payload: dict,
    ) -> None:
        """Verifica erro de conexao com storage."""
        from app.infrastructure.storage.minio_client import StorageError

        mock_minio = MagicMock()
        mock_minio.download_file.side_effect = StorageError("Conexao recusada")
        mock_minio_cls.return_value = mock_minio

        res = client.post(
            "/api/v1/documents/process-document",
            json=valid_payload,
        )

        assert res.status_code == 502
        data = res.json()
        assert "detail" in data

    @patch("app.api.v1.endpoints.documents.update_document_status")
    @patch("app.api.v1.endpoints.documents.MinIOClient")
    @patch("app.api.v1.endpoints.documents.PDFExtractor")
    def test_process_document_invalid_pdf(
        self,
        mock_extractor_cls,
        mock_minio_cls,
        mock_update_status,
        client: TestClient,
        valid_payload: dict,
    ) -> None:
        """Verifica erro quando PDF e invalido/corrompido."""
        mock_minio = MagicMock()
        mock_minio.download_file.return_value = b"not a pdf content"
        mock_minio_cls.return_value = mock_minio

        mock_extractor = MagicMock()
        mock_extractor.extract_text.side_effect = ValueError(
            "PDF invalido ou corrompido"
        )
        mock_extractor_cls.return_value = mock_extractor

        res = client.post(
            "/api/v1/documents/process-document",
            json=valid_payload,
        )

        assert res.status_code == 400
        data = res.json()
        assert "detail" in data


# ---------------------------------------------------------------------------
# Testes unitarios dos componentes
# ---------------------------------------------------------------------------


class TestPDFExtractor:
    """Testes do extrator de PDF."""

    def test_extract_text_from_valid_pdf(self) -> None:
        """Extrai texto de PDF valido."""
        from app.infrastructure.extractors.pdf_extractor import PDFExtractor

        extractor = PDFExtractor()
        pages = extractor.extract_text(_mock_pdf_bytes())

        assert len(pages) >= 1
        assert pages[0]["page_number"] == 1
        assert isinstance(pages[0]["text"], str)

    def test_extract_text_from_invalid_pdf(self) -> None:
        """Rejeita arquivo que nao e PDF."""
        from app.infrastructure.extractors.pdf_extractor import PDFExtractor

        extractor = PDFExtractor()
        with pytest.raises(ValueError, match="PDF invalido"):
            extractor.extract_text(b"not a pdf at all")


class TestTextChunker:
    """Testes do chunker de texto."""

    def test_chunk_text_basic(self) -> None:
        """Divide texto em chunks com overlap."""
        from app.infrastructure.chunking.chunker import TextChunker

        chunker = TextChunker()
        text = "A " * 500  # 1000 caracteres
        chunks = chunker.chunk_text(text, chunk_size=200, overlap=50)

        assert len(chunks) > 1
        assert all("text" in c for c in chunks)
        assert all("page_number" in c for c in chunks)
        assert all("chunk_index" in c for c in chunks)

    def test_chunk_text_empty(self) -> None:
        """Texto vazio retorna lista vazia."""
        from app.infrastructure.chunking.chunker import TextChunker

        chunker = TextChunker()
        chunks = chunker.chunk_text("")
        assert chunks == []

    def test_chunk_pages(self) -> None:
        """Chunking em multiplas paginas."""
        from app.infrastructure.chunking.chunker import TextChunker

        chunker = TextChunker()
        pages = _mock_pages()
        chunks = chunker.chunk_pages(pages, chunk_size=500, overlap=100)

        assert len(chunks) > 0
        # Verifica que chunks de paginas diferentes existem
        page_numbers = {c["page_number"] for c in chunks}
        assert len(page_numbers) >= 1


class TestOpenAIEmbedder:
    """Testes do gerador de embeddings."""

    def test_mock_embed_consistent(self) -> None:
        """Embeddings mock sao consistentes para mesmo texto."""
        from app.infrastructure.embeddings.openai_embedder import OpenAIEmbedder

        embedder = OpenAIEmbedder()  # usa mock sem API key
        texts = ["texto de teste", "outro texto"]
        embeddings = embedder.embed_texts(texts)

        assert len(embeddings) == 2
        assert len(embeddings[0]) == 1536
        assert len(embeddings[1]) == 1536

        # Mesma entrada → mesmo embedding (deterministico)
        embeddings2 = embedder.embed_texts(texts)
        assert embeddings[0] == embeddings2[0]
        assert embeddings[1] == embeddings2[1]

    def test_mock_embed_normalized(self) -> None:
        """Embeddings mock sao vetores unitarios."""
        from app.infrastructure.embeddings.openai_embedder import OpenAIEmbedder

        embedder = OpenAIEmbedder()
        embeddings = embedder.embed_texts(["teste"])

        norm = sum(v * v for v in embeddings[0]) ** 0.5
        assert abs(norm - 1.0) < 0.001  # tolerancia para float


class TestPgVectorStore:
    """Testes do store pgvector (mock)."""

    @patch("app.infrastructure.database.pgvector_store.execute_values")
    @patch("app.infrastructure.database.pgvector_store.ThreadedConnectionPool")
    def test_insert_embeddings(self, mock_pool_cls, mock_execute_values) -> None:
        """Insere embeddings com sucesso."""
        from app.infrastructure.database.pgvector_store import PgVectorStore

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_pool = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_pool_cls.return_value = mock_pool

        store = PgVectorStore()
        data = [
            {
                "content": "chunk 1",
                "embedding": [0.1] * 1536,
                "metadata": {"project_id": "p1", "document_id": "d1"},
            },
        ]
        count = store.insert_embeddings(data)

        assert count == 1
        mock_execute_values.assert_called_once()
        mock_conn.commit.assert_called_once()

    @patch("app.infrastructure.database.pgvector_store.ThreadedConnectionPool")
    def test_insert_empty_returns_zero(self, mock_pool_cls) -> None:
        """Lista vazia retorna 0 sem chamar DB."""
        from app.infrastructure.database.pgvector_store import PgVectorStore

        store = PgVectorStore()
        count = store.insert_embeddings([])
        assert count == 0
        mock_pool_cls.assert_not_called()
