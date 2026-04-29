"""
Rastreamento de falhas permanentes de indexacao.

Armazena itens que falharam apos todas as retentativas no MongoDB
para analise posterior e reprocessamento manual.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Optional

logger = logging.getLogger(__name__)

COLLECTION_NAME = "index_failures"


class FailureTracker:
    """
    Rastreia falhas permanentes de processamento de livros.

    Armazena no MongoDB para durabilidade e analise posterior.
    """

    def __init__(self, mongo_db) -> None:
        """
        Inicializa failure tracker.

        Args:
            mongo_db: instancia motor database (injetada via infra).
        """
        self._db = mongo_db
        self._collection = mongo_db.get_collection(COLLECTION_NAME)

    async def record_failure(
        self,
        stable_key: str,
        error: str,
        source_provider: Optional[str] = None,
        retry_count: int = 0,
    ) -> None:
        """
        Registra falha permanente de um livro.

        Se falha ja existe para o stable_key, incrementa retry_count
        e atualiza ultimo erro.

        Args:
            stable_key: chave estavel do livro.
            error: mensagem de erro.
            source_provider: provedor da fonte (ex: gutenberg).
            retry_count: numero de tentativas antes da falha.
        """
        now = datetime.now(UTC)

        # Verifica se ja existe falha para este stable_key
        existing = await self._collection.find_one({"stable_key": stable_key})

        if existing:
            # Atualiza falha existente
            await self._collection.update_one(
                {"stable_key": stable_key},
                {
                    "$set": {
                        "error": error,
                        "retry_count": existing.get("retry_count", 0) + 1,
                        "last_attempt": now,
                    }
                },
            )
            logger.warning(
                "Falha atualizada: stable_key=%s, retry_count=%d",
                stable_key,
                existing.get("retry_count", 0) + 1,
            )
        else:
            # Cria novo registro de falha
            doc = {
                "stable_key": stable_key,
                "source_provider": source_provider or "unknown",
                "error": error,
                "retry_count": retry_count,
                "last_attempt": now,
                "created_at": now,
            }
            await self._collection.insert_one(doc)
            logger.warning(
                "Falha registrada: stable_key=%s, error=%s",
                stable_key,
                error[:100],
            )

    async def get_failures(self, limit: int = 50) -> list[dict]:
        """
        Retorna lista de falhas registradas.

        Args:
            limit: numero maximo de registros.

        Returns:
            Lista de documentos de falha ordenados por last_attempt.
        """
        cursor = self._collection.find().sort("last_attempt", -1).limit(limit)
        failures = await cursor.to_list(length=limit)

        # Converte ObjectId para string para serializacao
        for failure in failures:
            if "_id" in failure:
                failure["_id"] = str(failure["_id"])
            # Converte datetime para ISO string
            for key in ("last_attempt", "created_at"):
                if key in failure and isinstance(failure[key], datetime):
                    failure[key] = failure[key].isoformat()

        return failures

    async def clear_failure(self, stable_key: str) -> bool:
        """
        Remove registro de falha para um livro.

        Usado quando o livro e reprocessado com sucesso.

        Args:
            stable_key: chave estavel do livro.

        Returns:
            True se registro foi removido.
        """
        result = await self._collection.delete_one({"stable_key": stable_key})
        if result.deleted_count > 0:
            logger.info("Falha removida: stable_key=%s", stable_key)
            return True
        return False

    async def get_failure_count(self) -> int:
        """
        Retorna numero total de falhas registradas.

        Returns:
            Contagem de falhas.
        """
        return await self._collection.count_documents({})
