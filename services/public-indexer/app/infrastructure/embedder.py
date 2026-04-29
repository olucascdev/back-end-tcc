"""
Geracao de embeddings via OpenAI API.

Suporta modo mock para testes sem chave de API e batching
automatico para chamadas eficientes.
"""

from __future__ import annotations

import logging
import random
from typing import Optional

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 1536
MAX_BATCH_SIZE = 100


class OpenAIEmbedder:
    """
    Gera embeddings de textos usando OpenAI API.

    Suporta modo mock (vetores aleatorios deterministicos) quando
    OPENAI_API_KEY nao esta configurada.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "text-embedding-ada-002",
        max_retries: int = 3,
    ) -> None:
        """
        Inicializa embedder.

        Args:
            api_key: chave da API OpenAI. Se vazia, usa modo mock.
            model: modelo de embedding a usar.
            max_retries: numero maximo de retentativas.
        """
        self._api_key = api_key or ""
        self._model = model
        self._max_retries = max_retries
        self._mock_mode = not self._api_key.strip()
        self._client = None

        if not self._mock_mode:
            try:
                from openai import AsyncOpenAI

                self._client = AsyncOpenAI(api_key=self._api_key)
                logger.info("OpenAI Embedder inicializado com modelo %s", model)
            except ImportError:
                logger.warning("openai package nao instalada, usando modo mock")
                self._mock_mode = True
        else:
            logger.info("OpenAI Embedder em modo mock (sem API key)")

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        Gera embeddings para lista de textos.

        Faz batching automatico com maximo de 100 textos por chamada.

        Args:
            texts: lista de textos para embeddar.

        Returns:
            Lista de vetores de embedding (list[float]).

        Raises:
            RuntimeError se todas as retentativas falharem.
        """
        if not texts:
            return []

        # Filtra textos vazios mantendo indices
        valid_texts = []
        indices_map = []
        for i, text in enumerate(texts):
            if text and text.strip():
                valid_texts.append(text.strip())
                indices_map.append(i)

        if not valid_texts:
            # Retorna vetores zerados para todos os indices
            return [[0.0] * EMBEDDING_DIM for _ in range(len(texts))]

        # Processa em batches
        all_embeddings: list[Optional[list[float]]] = [None] * len(texts)

        for batch_start in range(0, len(valid_texts), MAX_BATCH_SIZE):
            batch = valid_texts[batch_start : batch_start + MAX_BATCH_SIZE]
            batch_indices = indices_map[batch_start : batch_start + MAX_BATCH_SIZE]

            embeddings = await self._embed_batch_with_retry(batch)

            for idx, embedding in zip(batch_indices, embeddings):
                all_embeddings[idx] = embedding

        # Preenche indices vazios com vetores zerados
        for i, emb in enumerate(all_embeddings):
            if emb is None:
                all_embeddings[i] = [0.0] * EMBEDDING_DIM

        return all_embeddings

    async def _embed_batch_with_retry(self, texts: list[str]) -> list[list[float]]:
        """
        Gera embeddings para um batch com retry exponencial.

        Args:
            texts: batch de textos.

        Returns:
            Lista de embeddings.
        """
        last_exc: Optional[Exception] = None

        for attempt in range(1, self._max_retries + 1):
            try:
                if self._mock_mode:
                    return self._mock_embed(texts)

                return await self._real_embed(texts)
            except Exception as exc:
                last_exc = exc
                is_transient = self._is_transient_error(exc)

                if is_transient and attempt < self._max_retries:
                    import asyncio

                    delay = 2 ** (attempt - 1) + random.uniform(0, 1)
                    logger.warning(
                        "Embedding falhou (tentativa %d/%d), retry em %.1fs: %s",
                        attempt,
                        self._max_retries,
                        delay,
                        exc,
                    )
                    await asyncio.sleep(delay)
                else:
                    error_type = "transient" if is_transient else "permanent"
                    logger.error(
                        "Embedding falhou (%s, tentativa %d/%d): %s",
                        error_type,
                        attempt,
                        self._max_retries,
                        exc,
                    )
                    if not is_transient:
                        raise

        raise last_exc or RuntimeError(
            f"Falha apos {self._max_retries} tentativas de embedding"
        )

    async def _real_embed(self, texts: list[str]) -> list[list[float]]:
        """Chama API real da OpenAI."""
        if self._client is None:
            raise RuntimeError("OpenAI client nao inicializado")

        response = await self._client.embeddings.create(
            model=self._model,
            input=texts,
        )

        # Ordena por indice para garantir ordem correta
        sorted_data = sorted(response.data, key=lambda x: x.index)
        return [item.embedding for item in sorted_data]

    @staticmethod
    def _mock_embed(texts: list[str]) -> list[list[float]]:
        """
        Gera vetores aleatorios deterministicos para modo mock.

        Usa hash do texto como seed para reproducibilidade.

        Args:
            texts: lista de textos.

        Returns:
            Lista de vetores aleatorios de dimensao EMBEDDING_DIM.
        """
        embeddings = []
        for text in texts:
            # Seed deterministica baseada no texto
            seed = hash(text) & 0xFFFFFFFF
            rng = random.Random(seed)
            embedding = [rng.gauss(0, 0.01) for _ in range(EMBEDDING_DIM)]
            # Normaliza para unit vector
            magnitude = sum(x * x for x in embedding) ** 0.5
            if magnitude > 0:
                embedding = [x / magnitude for x in embedding]
            embeddings.append(embedding)
        return embeddings

    @staticmethod
    def _is_transient_error(exc: Exception) -> bool:
        """
        Verifica se erro e transiente (retryavel).

        Args:
            exc: excecao capturada.

        Returns:
            True se erro e transiente.
        """
        error_str = str(exc).lower()
        transient_keywords = [
            "timeout",
            "connection",
            "rate limit",
            "429",
            "500",
            "502",
            "503",
            "504",
            "service unavailable",
            "internal server error",
        ]
        return any(keyword in error_str for keyword in transient_keywords)

    @property
    def is_mock_mode(self) -> bool:
        """Retorna True se embedder esta em modo mock."""
        return self._mock_mode
