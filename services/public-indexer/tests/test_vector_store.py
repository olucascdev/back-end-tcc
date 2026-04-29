"""
Testes do PublicVectorStore.

Verifica insercao bulk, verificacao de fingerprint e cleanup.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.infrastructure.vector_store import PublicVectorStore


def make_async_cm(mock_conn: MagicMock):
    """Cria um async context manager mock."""
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=mock_conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


@pytest.fixture
def mock_pg_client() -> MagicMock:
    """Mock do cliente PostgreSQL."""
    client = MagicMock()
    return client


@pytest.fixture
def vector_store(mock_pg_client: MagicMock) -> PublicVectorStore:
    """Vector store com mock injetado."""
    return PublicVectorStore(pg_client=mock_pg_client)


class TestInsertEmbeddings:
    """Testes de insercao de embeddings."""

    @pytest.mark.asyncio
    async def test_insert_empty_returns_zero(
        self, vector_store: PublicVectorStore
    ) -> None:
        """Verifica que insercao vazia retorna 0."""
        result = await vector_store.insert_embeddings([])
        assert result == 0

    @pytest.mark.asyncio
    async def test_insert_single_record(
        self,
        vector_store: PublicVectorStore,
        mock_pg_client: MagicMock,
    ) -> None:
        """Verifica insercao de um unico registro."""
        pytest.importorskip("psycopg.extras")

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor = MagicMock(return_value=mock_cursor)
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)

        mock_pg_client.get_connection = MagicMock(return_value=make_async_cm(mock_conn))

        record = {
            "content": "Test content",
            "embedding": [0.1] * 1536,
            "metadata": {
                "source_type": "public_library",
                "source_provider": "gutenberg",
                "source_id": "42",
                "artifact_key": "gutenberg/42/v1.txt",
                "checksum": "abc123",
                "chunk_version": 1,
            },
        }

        result = await vector_store.insert_embeddings([record])
        assert result == 1
        mock_cursor.execute.assert_called()

    @pytest.mark.asyncio
    async def test_insert_multiple_records(
        self,
        vector_store: PublicVectorStore,
        mock_pg_client: MagicMock,
    ) -> None:
        """Verifica insercao de multiplos registros."""
        pytest.importorskip("psycopg.extras")

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor = MagicMock(return_value=mock_cursor)
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)

        mock_pg_client.get_connection = MagicMock(return_value=make_async_cm(mock_conn))

        records = [
            {
                "content": f"Content {i}",
                "embedding": [0.1] * 1536,
                "metadata": {
                    "source_type": "public_library",
                    "source_provider": "gutenberg",
                    "source_id": "42",
                    "artifact_key": "gutenberg/42/v1.txt",
                    "checksum": "abc123",
                    "chunk_version": 1,
                },
            }
            for i in range(5)
        ]

        result = await vector_store.insert_embeddings(records)
        assert result == 5
        mock_cursor.execute.assert_called()


class TestFingerprintCheck:
    """Testes de verificacao de fingerprint."""

    @pytest.mark.asyncio
    async def test_fingerprint_exists(
        self,
        vector_store: PublicVectorStore,
        mock_pg_client: MagicMock,
    ) -> None:
        """Verifica deteccao de fingerprint existente."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone = MagicMock(return_value=(True,))
        mock_conn.cursor = MagicMock(return_value=mock_cursor)
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)

        mock_pg_client.get_connection = MagicMock(return_value=make_async_cm(mock_conn))

        result = await vector_store.check_existing_fingerprint(
            source_id="42",
            checksum="abc123",
            chunk_version=1,
        )

        assert result is True
        mock_cursor.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_fingerprint_not_exists(
        self,
        vector_store: PublicVectorStore,
        mock_pg_client: MagicMock,
    ) -> None:
        """Verifica que fingerprint inexistente retorna False."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone = MagicMock(return_value=(False,))
        mock_conn.cursor = MagicMock(return_value=mock_cursor)
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)

        mock_pg_client.get_connection = MagicMock(return_value=make_async_cm(mock_conn))

        result = await vector_store.check_existing_fingerprint(
            source_id="99",
            checksum="xyz789",
        )

        assert result is False


class TestDeleteByFingerprint:
    """Testes de remocao por fingerprint."""

    @pytest.mark.asyncio
    async def test_delete_existing(
        self,
        vector_store: PublicVectorStore,
        mock_pg_client: MagicMock,
    ) -> None:
        """Verifica remocao de embeddings existentes."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 3
        mock_conn.cursor = MagicMock(return_value=mock_cursor)
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)

        mock_pg_client.get_connection = MagicMock(return_value=make_async_cm(mock_conn))

        result = await vector_store.delete_by_fingerprint(
            source_id="42",
            checksum="abc123",
        )

        assert result == 3
        mock_cursor.execute.assert_called_once()


class TestCountBySource:
    """Testes de contagem por fonte."""

    @pytest.mark.asyncio
    async def test_count_by_source(
        self,
        vector_store: PublicVectorStore,
        mock_pg_client: MagicMock,
    ) -> None:
        """Verifica contagem de embeddings por source_id."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone = MagicMock(return_value=(42,))
        mock_conn.cursor = MagicMock(return_value=mock_cursor)
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)

        mock_pg_client.get_connection = MagicMock(return_value=make_async_cm(mock_conn))

        result = await vector_store.count_by_source(source_id="42")

        assert result == 42
