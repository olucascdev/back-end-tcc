"""
Testes unitarios dos contratos internos v1 (schemas Pydantic).

Cobertura:
- Criacao valida de cada model com dados minimos e completos.
- Validacao de campos obrigatorios ausentes.
- Serializacao e deserializacao JSON (model_dump / model_validate).
"""

from __future__ import annotations

import json
from datetime import datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.contracts_v1 import (
    ChatRequest,
    ChatResponse,
    CompareRequest,
    CompareResponse,
    DocumentStatusWebhook,
    ProcessDocumentRequest,
    ProcessDocumentResponse,
    Source,
    SummarizeRequest,
    SummarizeResponse,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_source() -> dict:
    return {"document": "doc.pdf", "page": 1, "score": 0.95}


# ---------------------------------------------------------------------------
# Source
# ---------------------------------------------------------------------------


class TestSource:
    def test_valid_minimal(self):
        s = Source(**_valid_source())
        assert s.document == "doc.pdf"
        assert s.section is None

    def test_valid_full(self):
        s = Source(document="doc.pdf", page=5, section="Intro", score=0.88)
        assert s.section == "Intro"

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            Source(page=1, score=0.5)  # document missing

    def test_json_roundtrip(self):
        s = Source(**_valid_source())
        data = s.model_dump(mode="json")
        s2 = Source.model_validate(data)
        assert s2.document == s.document


# ---------------------------------------------------------------------------
# ProcessDocumentRequest
# ---------------------------------------------------------------------------


class TestProcessDocumentRequest:
    def test_valid_minimal(self):
        req = ProcessDocumentRequest(
            project_id=uuid4(),
            document_id=uuid4(),
            storage_key="s3://bucket/key",
        )
        assert req.source_type == "user_upload"
        assert req.metadata is None

    def test_valid_full(self):
        req = ProcessDocumentRequest(
            project_id=uuid4(),
            document_id=uuid4(),
            storage_key="s3://bucket/key",
            source_type="import",
            metadata={"author": "test"},
        )
        assert req.source_type == "import"

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            ProcessDocumentRequest(project_id=uuid4(), document_id=uuid4())

    def test_json_roundtrip(self):
        req = ProcessDocumentRequest(
            project_id=uuid4(),
            document_id=uuid4(),
            storage_key="s3://bucket/key",
        )
        data = json.loads(req.model_dump_json())
        assert data["storage_key"] == "s3://bucket/key"


# ---------------------------------------------------------------------------
# ProcessDocumentResponse
# ---------------------------------------------------------------------------


class TestProcessDocumentResponse:
    @pytest.mark.parametrize("status", ["pending", "processing", "ready", "error"])
    def test_valid_statuses(self, status):
        resp = ProcessDocumentResponse(
            document_id=uuid4(),
            status=status,
        )
        assert resp.status == status

    def test_invalid_status(self):
        with pytest.raises(ValidationError):
            ProcessDocumentResponse(document_id=uuid4(), status="unknown")

    def test_json_roundtrip(self):
        resp = ProcessDocumentResponse(
            document_id=uuid4(),
            status="ready",
            chunks_count=42,
        )
        data = json.loads(resp.model_dump_json())
        assert data["chunks_count"] == 42


# ---------------------------------------------------------------------------
# ChatRequest
# ---------------------------------------------------------------------------


class TestChatRequest:
    def test_valid_minimal(self):
        req = ChatRequest(
            project_id=uuid4(),
            session_id="sess-1",
            message="Ola",
        )
        assert req.filters is None

    def test_valid_with_filters(self):
        req = ChatRequest(
            project_id=uuid4(),
            session_id="sess-1",
            message="Ola",
            filters={"year": 2024},
        )
        assert req.filters["year"] == 2024

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            ChatRequest(project_id=uuid4(), session_id="s")

    def test_json_roundtrip(self):
        req = ChatRequest(project_id=uuid4(), session_id="s", message="hi")
        data = json.loads(req.model_dump_json())
        assert data["message"] == "hi"


# ---------------------------------------------------------------------------
# ChatResponse
# ---------------------------------------------------------------------------


class TestChatResponse:
    def test_valid(self):
        resp = ChatResponse(
            answer="Sim.",
            sources=[Source(**_valid_source())],
            session_id="sess-1",
        )
        assert isinstance(resp.created_at, datetime)

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            ChatResponse(sources=[], session_id="s")

    def test_json_roundtrip(self):
        resp = ChatResponse(answer="Sim.", sources=[], session_id="s")
        data = json.loads(resp.model_dump_json())
        assert data["answer"] == "Sim."


# ---------------------------------------------------------------------------
# SummarizeRequest
# ---------------------------------------------------------------------------


class TestSummarizeRequest:
    def test_valid_default_format(self):
        req = SummarizeRequest(document_id=uuid4(), project_id=uuid4())
        assert req.format == "structured"

    def test_valid_custom_format(self):
        req = SummarizeRequest(
            document_id=uuid4(),
            project_id=uuid4(),
            format="narrative",
        )
        assert req.format == "narrative"

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            SummarizeRequest(document_id=uuid4())

    def test_json_roundtrip(self):
        req = SummarizeRequest(document_id=uuid4(), project_id=uuid4())
        data = json.loads(req.model_dump_json())
        assert data["format"] == "structured"


# ---------------------------------------------------------------------------
# SummarizeResponse
# ---------------------------------------------------------------------------


class TestSummarizeResponse:
    def test_valid(self):
        resp = SummarizeResponse(
            document_id=uuid4(),
            summary={
                "objective": "X",
                "methodology": "Y",
                "results": "Z",
                "conclusion": "W",
            },
        )
        assert isinstance(resp.created_at, datetime)

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            SummarizeResponse(document_id=uuid4())

    def test_json_roundtrip(self):
        resp = SummarizeResponse(
            document_id=uuid4(),
            summary={
                "objective": "X",
                "methodology": "Y",
                "results": "Z",
                "conclusion": "W",
            },
        )
        data = json.loads(resp.model_dump_json())
        assert data["summary"]["objective"] == "X"


# ---------------------------------------------------------------------------
# CompareRequest
# ---------------------------------------------------------------------------


class TestCompareRequest:
    def test_valid(self):
        req = CompareRequest(
            project_id=uuid4(),
            document_ids=[uuid4(), uuid4()],
            theme="metodologia",
        )
        assert len(req.document_ids) == 2

    def test_single_document_rejected(self):
        with pytest.raises(ValidationError):
            CompareRequest(
                project_id=uuid4(),
                document_ids=[uuid4()],
                theme="tema",
            )

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            CompareRequest(project_id=uuid4(), document_ids=[uuid4(), uuid4()])

    def test_json_roundtrip(self):
        req = CompareRequest(
            project_id=uuid4(),
            document_ids=[uuid4(), uuid4()],
            theme="tema",
        )
        data = json.loads(req.model_dump_json())
        assert data["theme"] == "tema"


# ---------------------------------------------------------------------------
# CompareResponse
# ---------------------------------------------------------------------------


class TestCompareResponse:
    def test_valid(self):
        resp = CompareResponse(
            project_id=uuid4(),
            comparison={"doc1": "A", "doc2": "B"},
            sources=[Source(**_valid_source())],
        )
        assert isinstance(resp.created_at, datetime)

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            CompareResponse(project_id=uuid4(), sources=[])

    def test_json_roundtrip(self):
        resp = CompareResponse(
            project_id=uuid4(),
            comparison={"a": "b"},
            sources=[],
        )
        data = json.loads(resp.model_dump_json())
        assert data["comparison"]["a"] == "b"


# ---------------------------------------------------------------------------
# DocumentStatusWebhook
# ---------------------------------------------------------------------------


class TestDocumentStatusWebhook:
    def test_valid_minimal(self):
        wh = DocumentStatusWebhook(
            document_id=uuid4(),
            project_id=uuid4(),
            status="ready",
        )
        assert isinstance(wh.timestamp, datetime)

    def test_valid_full(self):
        wh = DocumentStatusWebhook(
            document_id=uuid4(),
            project_id=uuid4(),
            status="error",
            error_message="timeout",
            metadata={"retry": 3},
        )
        assert wh.error_message == "timeout"

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            DocumentStatusWebhook(document_id=uuid4(), project_id=uuid4())

    def test_json_roundtrip(self):
        wh = DocumentStatusWebhook(
            document_id=uuid4(),
            project_id=uuid4(),
            status="processing",
        )
        data = json.loads(wh.model_dump_json())
        assert data["status"] == "processing"
