"""
Armazenamento de embeddings em PostgreSQL com pgvector.

Operacoes bulk insert, verificacao de idempotencia por fingerprint
e cleanup de embeddings obsoletos.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from psycopg.types.json import Jsonb

from app.infrastructure.clients import PostgresClient

logger = logging.getLogger(__name__)

TABLE_NAME = "document_embeddings"


class PublicVectorStore:
    """
    Armazena e consulta embeddings publicos em PostgreSQL/pgvector.

    Usa a tabela unificada document_embeddings com coluna metadata JSONB.
    """

    def __init__(self, pg_client: PostgresClient) -> None:
        """
        Inicializa vector store.

        Args:
            pg_client: cliente PostgreSQL com pool de conexoes.
        """
        self._pg_client = pg_client

    async def insert_embeddings(self, records: list[dict]) -> int:
        """
        Insere embeddings em bulk na tabela document_embeddings.

        Cada record deve ter: {content, embedding, metadata}
        onde metadata e um dict compativel com EmbeddingMetadata.

        Args:
            records: lista de registros para inserir.

        Returns:
            Numero de registros inseridos.
        """
        if not records:
            return 0

        async with self._pg_client.get_connection() as conn:
            with conn.cursor() as cur:
                # Prepara dados para insert bulk
                values = []
                for record in records:
                    content = record["content"]
                    embedding = record["embedding"]
                    metadata = record["metadata"]

                    # Converte metadata para JSONB
                    if isinstance(metadata, dict):
                        metadata_json = Jsonb(metadata)
                    else:
                        metadata_json = Jsonb(metadata)

                    values.append((content, embedding, metadata_json))

                # Insert bulk usando execute_values para performance
                from psycopg.extras import execute_values

                execute_values(
                    cur,
                    f"""
                    INSERT INTO {TABLE_NAME} (content, embedding, metadata)
                    VALUES %s
                    """,
                    values,
                    template="(%s, %s::vector, %s)",
                )

                inserted = len(values)
                logger.info("Embeddings inseridos: count=%d", inserted)
                return inserted

    async def check_existing_fingerprint(
        self,
        source_id: str,
        checksum: str,
        chunk_version: int = 1,
    ) -> bool:
        """
        Verifica se embeddings ja existem para um fingerprint.

        Fingerprint = source_id + checksum + chunk_version.

        Args:
            source_id: identificador unico na fonte.
            checksum: hash do conteudo.
            chunk_version: versao do chunking.

        Returns:
            True se embeddings ja existem.
        """
        async with self._pg_client.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT EXISTS (
                        SELECT 1 FROM {TABLE_NAME}
                        WHERE metadata->>'source_id' = %s
                          AND metadata->>'checksum' = %s
                          AND (metadata->>'chunk_version')::int = %s
                        LIMIT 1
                    )
                    """,
                    (source_id, checksum, chunk_version),
                )
                result = cur.fetchone()
                exists = result[0] if result else False
                if exists:
                    logger.debug(
                        "Fingerprint existente: source_id=%s, checksum=%s",
                        source_id,
                        checksum[:8],
                    )
                return exists

    async def delete_by_fingerprint(
        self,
        source_id: str,
        checksum: str,
    ) -> int:
        """
        Remove embeddings por fingerprint para reprocessamento limpo.

        Args:
            source_id: identificador unico na fonte.
            checksum: hash do conteudo.

        Returns:
            Numero de registros removidos.
        """
        async with self._pg_client.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    DELETE FROM {TABLE_NAME}
                    WHERE metadata->>'source_id' = %s
                      AND metadata->>'checksum' = %s
                    """,
                    (source_id, checksum),
                )
                deleted = cur.rowcount
                logger.info(
                    "Embeddings removidos por fingerprint: count=%d, source_id=%s",
                    deleted,
                    source_id,
                )
                return deleted

    async def count_by_source(self, source_id: str) -> int:
        """
        Conta embeddings por source_id.

        Args:
            source_id: identificador da fonte.

        Returns:
            Numero de embeddings para a fonte.
        """
        async with self._pg_client.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT COUNT(*) FROM {TABLE_NAME}
                    WHERE metadata->>'source_id' = %s
                    """,
                    (source_id,),
                )
                result = cur.fetchone()
                return result[0] if result else 0
