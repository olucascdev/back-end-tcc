"""
Endpoints de processamento de documentos.

Recebe requisicoes do gateway Go para processar documentos recem-ingestados.
Pipeline: download MinIO → extracao PDF → chunking → embeddings → pgvector.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.core.config import Settings
from app.core.database import update_document_status
from app.infrastructure.chunking.chunker import TextChunker
from app.infrastructure.database.pgvector_store import PgVectorStore
from app.infrastructure.embeddings.openai_embedder import OpenAIEmbedder
from app.infrastructure.extractors.pdf_extractor import PDFExtractor
from app.infrastructure.storage.minio_client import MinIOClient, StorageError
from app.schemas.contracts_v1 import ProcessDocumentRequest, ProcessDocumentResponse

logger = logging.getLogger(__name__)

router = APIRouter()


def _process_document_sync(
    req: ProcessDocumentRequest, settings: Settings
) -> ProcessDocumentResponse:
    """Executa pipeline completo de processamento de documento.

    Etapas:
    1. Download do arquivo do MinIO/S3
    2. Extracao de texto do PDF
    3. Chunking do texto
    4. Geracao de embeddings
    5. Persistencia no pgvector
    6. Atualizacao de status no NeonDB

    Args:
        req: requisicao com project_id, document_id, storage_key.
        settings: configuracoes do servico.

    Returns:
        Response com status e contagem de chunks.

    Raises:
        HTTPException: se qualquer etapa falhar.
    """
    try:
        # 1. Download do arquivo
        storage = MinIOClient(settings)
        file_bytes = storage.download_file(req.storage_key)
        logger.info(
            "Documento baixado: key=%s size=%d bytes", req.storage_key, len(file_bytes)
        )

        # 2. Extracao de texto
        extractor = PDFExtractor()
        pages = extractor.extract_text(file_bytes)
        total_text_len = sum(len(p["text"]) for p in pages)
        logger.info(
            "Texto extraido: %d paginas, %d caracteres", len(pages), total_text_len
        )

        # 3. Chunking
        chunker = TextChunker()
        chunks = chunker.chunk_pages(
            pages,
            chunk_size=settings.CHUNK_SIZE,
            overlap=settings.CHUNK_OVERLAP,
        )
        logger.info("Chunks gerados: %d", len(chunks))

        # 4. Geracao de embeddings
        embedder = OpenAIEmbedder(settings)
        chunk_texts = [c["text"] for c in chunks]
        embeddings = embedder.embed_texts(chunk_texts)
        logger.info("Embeddings gerados: %d vetores", len(embeddings))

        # 5. Persistencia no pgvector
        embeddings_data = []
        for chunk, embedding in zip(chunks, embeddings):
            embeddings_data.append(
                {
                    "content": chunk["text"],
                    "embedding": embedding,
                    "metadata": {
                        "project_id": str(req.project_id),
                        "document_id": str(req.document_id),
                        "page_number": chunk["page_number"],
                        "chunk_index": chunk["chunk_index"],
                    },
                }
            )

        store = PgVectorStore(settings)
        inserted = store.insert_embeddings(embeddings_data)
        logger.info("Embeddings persistidos: %d registros", inserted)

        # 6. Atualiza status no NeonDB
        update_document_status(
            document_id=str(req.document_id),
            status="ready",
            chunks_count=len(chunks),
            settings=settings,
        )

        return ProcessDocumentResponse(
            document_id=req.document_id,
            status="ready",
            chunks_count=len(chunks),
            processed_at=datetime.now(UTC),
            error_message=None,
        )

    except FileNotFoundError as exc:
        logger.error("Arquivo nao encontrado no storage: %s", exc)
        _set_document_error(req, "Arquivo nao encontrado no storage")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Arquivo nao encontrado: {exc}",
        ) from exc

    except ValueError as exc:
        logger.error("Erro de validacao no processamento: %s", exc)
        _set_document_error(req, f"Erro de validacao: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erro de validacao: {exc}",
        ) from exc

    except StorageError as exc:
        logger.error("Erro de storage: %s", exc)
        _set_document_error(req, f"Erro de storage: {exc}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Erro ao acessar storage: {exc}",
        ) from exc

    except Exception as exc:
        logger.error("Erro inesperado no processamento: %s", exc, exc_info=True)
        _set_document_error(req, f"Erro interno: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro interno no processamento: {exc}",
        ) from exc


def _set_document_error(req: ProcessDocumentRequest, message: str) -> None:
    """Atualiza status do documento para error no NeonDB."""
    try:
        update_document_status(
            document_id=str(req.document_id),
            status="error",
            error_message=message,
        )
    except Exception as db_exc:
        logger.error("Falha ao atualizar status de erro no DB: %s", db_exc)


@router.post("/process-document", response_model=ProcessDocumentResponse)
def process_document(req: ProcessDocumentRequest) -> ProcessDocumentResponse:
    """Processa documento completo: download, extracao, chunking, embedding, persistencia.

    Endpoint sincrono — o gateway Go deve chamar com timeout adequado.
    Para documentos grandes, considerar migrar para processamento assincrono via fila.
    """
    settings = Settings()
    logger.info(
        "Iniciando processamento: project_id=%s document_id=%s storage_key=%s",
        req.project_id,
        req.document_id,
        req.storage_key,
    )
    return _process_document_sync(req, settings)
