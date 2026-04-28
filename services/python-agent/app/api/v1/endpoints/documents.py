"""
Endpoints de processamento de documentos.

Recebe requisicoes do gateway Go para processar documentos recem-ingestados.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter

from app.schemas.contracts_v1 import ProcessDocumentRequest, ProcessDocumentResponse

router = APIRouter()


@router.post("/process-document", response_model=ProcessDocumentResponse)
def process_document(req: ProcessDocumentRequest) -> ProcessDocumentResponse:
    """Aceita requisicao de processamento e retorna status inicial.

    Stub: retorna status 'processing' com dados mock.
    Implementacao real fara ingestao, chunking e embedding assincrono.
    """
    return ProcessDocumentResponse(
        document_id=req.document_id,
        status="processing",
        chunks_count=0,
        processed_at=None,
        error_message=None,
    )
