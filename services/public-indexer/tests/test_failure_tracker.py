"""
Testes do FailureTracker.

Verifica registro, consulta e limpeza de falhas permanentes.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.infrastructure.dlq import FailureTracker


@pytest.fixture
def mock_mongo_db() -> MagicMock:
    """Mock do database MongoDB."""
    db = MagicMock()
    collection = MagicMock()
    collection.find_one = AsyncMock(return_value=None)
    collection.insert_one = AsyncMock()
    collection.update_one = AsyncMock()
    collection.delete_one = AsyncMock()
    collection.find = MagicMock()
    collection.count_documents = AsyncMock(return_value=0)
    db.get_collection = MagicMock(return_value=collection)
    return db


@pytest.fixture
def tracker(mock_mongo_db: MagicMock) -> FailureTracker:
    """Failure tracker com mock injetado."""
    return FailureTracker(mongo_db=mock_mongo_db)


class TestRecordFailure:
    """Testes de registro de falhas."""

    @pytest.mark.asyncio
    async def test_record_new_failure(
        self, tracker: FailureTracker, mock_mongo_db: MagicMock
    ) -> None:
        """Verifica registro de nova falha."""
        collection = mock_mongo_db.get_collection.return_value

        await tracker.record_failure(
            stable_key="gutenberg:42",
            error="Download failed",
            source_provider="gutenberg",
        )

        collection.insert_one.assert_called_once()
        call_args = collection.insert_one.call_args[0][0]
        assert call_args["stable_key"] == "gutenberg:42"
        assert call_args["error"] == "Download failed"
        assert call_args["source_provider"] == "gutenberg"

    @pytest.mark.asyncio
    async def test_record_existing_failure_updates(
        self, tracker: FailureTracker, mock_mongo_db: MagicMock
    ) -> None:
        """Verifica que falha existente e atualizada."""
        collection = mock_mongo_db.get_collection.return_value
        collection.find_one = AsyncMock(
            return_value={"stable_key": "gutenberg:42", "retry_count": 1}
        )

        await tracker.record_failure(
            stable_key="gutenberg:42",
            error="New error",
            source_provider="gutenberg",
        )

        # Deve atualizar, nao inserir
        collection.update_one.assert_called_once()
        collection.insert_one.assert_not_called()

    @pytest.mark.asyncio
    async def test_record_failure_default_provider(
        self, tracker: FailureTracker, mock_mongo_db: MagicMock
    ) -> None:
        """Verifica que provider default e 'unknown'."""
        collection = mock_mongo_db.get_collection.return_value

        await tracker.record_failure(
            stable_key="hash:abc123",
            error="Error",
        )

        call_args = collection.insert_one.call_args[0][0]
        assert call_args["source_provider"] == "unknown"


class TestGetFailures:
    """Testes de consulta de falhas."""

    @pytest.mark.asyncio
    async def test_get_failures(
        self, tracker: FailureTracker, mock_mongo_db: MagicMock
    ) -> None:
        """Verifica consulta de falhas."""
        from datetime import UTC, datetime

        collection = mock_mongo_db.get_collection.return_value
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(
            return_value=[
                {
                    "_id": MagicMock(),
                    "stable_key": "gutenberg:42",
                    "error": "Error 1",
                    "last_attempt": datetime.now(UTC),
                    "created_at": datetime.now(UTC),
                }
            ]
        )
        mock_cursor.sort = MagicMock(return_value=mock_cursor)
        mock_cursor.limit = MagicMock(return_value=mock_cursor)
        collection.find = MagicMock(return_value=mock_cursor)

        failures = await tracker.get_failures(limit=10)

        assert len(failures) == 1
        assert failures[0]["stable_key"] == "gutenberg:42"
        # _id deve ser convertido para string
        assert isinstance(failures[0]["_id"], str)

    @pytest.mark.asyncio
    async def test_get_failures_empty(
        self, tracker: FailureTracker, mock_mongo_db: MagicMock
    ) -> None:
        """Verifica consulta quando nao ha falhas."""
        collection = mock_mongo_db.get_collection.return_value
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=[])
        mock_cursor.sort = MagicMock(return_value=mock_cursor)
        mock_cursor.limit = MagicMock(return_value=mock_cursor)
        collection.find = MagicMock(return_value=mock_cursor)

        failures = await tracker.get_failures()

        assert failures == []


class TestClearFailure:
    """Testes de limpeza de falhas."""

    @pytest.mark.asyncio
    async def test_clear_existing_failure(
        self, tracker: FailureTracker, mock_mongo_db: MagicMock
    ) -> None:
        """Verifica remocao de falha existente."""
        collection = mock_mongo_db.get_collection.return_value
        collection.delete_one = AsyncMock()
        collection.delete_one.return_value.deleted_count = 1

        result = await tracker.clear_failure("gutenberg:42")

        assert result is True
        collection.delete_one.assert_called_once_with({"stable_key": "gutenberg:42"})

    @pytest.mark.asyncio
    async def test_clear_nonexistent_failure(
        self, tracker: FailureTracker, mock_mongo_db: MagicMock
    ) -> None:
        """Verifica remocao de falha inexistente."""
        collection = mock_mongo_db.get_collection.return_value
        mock_result = MagicMock()
        mock_result.deleted_count = 0
        collection.delete_one = AsyncMock(return_value=mock_result)

        result = await tracker.clear_failure("gutenberg:999")

        assert result is False


class TestFailureCount:
    """Testes de contagem de falhas."""

    @pytest.mark.asyncio
    async def test_get_failure_count(
        self, tracker: FailureTracker, mock_mongo_db: MagicMock
    ) -> None:
        """Verifica contagem de falhas."""
        collection = mock_mongo_db.get_collection.return_value
        collection.count_documents = AsyncMock(return_value=5)

        count = await tracker.get_failure_count()

        assert count == 5
