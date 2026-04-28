"""
Gerador de embeddings via OpenAI API.

Usa modelo text-embedding-3-small. Inclui fallback mock para
desenvolvimento quando OPENAI_API_KEY nao esta configurada.
"""

from __future__ import annotations

import logging
import hashlib
import random

from app.core.config import Settings

logger = logging.getLogger(__name__)

# Dimensao padrao do modelo text-embedding-3-small
EMBEDDING_DIM = 1536


class OpenAIEmbedder:
    """Gera embeddings de texto usando OpenAI ou fallback mock."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or Settings()
        self._use_mock = not self._settings.OPENAI_API_KEY

        if self._use_mock:
            logger.warning(
                "OPENAI_API_KEY nao configurada; usando embeddings mock para desenvolvimento."
            )
        else:
            from openai import OpenAI

            self._client = OpenAI(api_key=self._settings.OPENAI_API_KEY)
            self._model = self._settings.EMBEDDING_MODEL

    def embed_query(self, text: str) -> list[float]:
        """Gera embedding para uma unica string de consulta.

        Args:
            text: texto da pergunta ou consulta.

        Returns:
            Embedding como list[float].
        """
        if self._use_mock:
            return self._mock_embed([text])[0]

        try:
            response = self._client.embeddings.create(
                model=self._model,
                input=text,
            )
            return response.data[0].embedding
        except Exception as exc:
            logger.error("Erro ao gerar embedding de consulta: %s", exc)
            raise EmbeddingError(
                f"Falha ao gerar embedding de consulta: {exc}"
            ) from exc

    def embed_texts(self, texts: list[str], batch_size: int = 100) -> list[list[float]]:
        """Gera embeddings para uma lista de textos.

        Processa em batches para evitar rate limit da API.

        Args:
            texts: lista de strings para gerar embeddings.
            batch_size: tamanho do batch por chamada API.

        Returns:
            Lista de embeddings (cada um e list[float]).
        """
        if self._use_mock:
            return self._mock_embed(texts)

        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            try:
                response = self._client.embeddings.create(
                    model=self._model,
                    input=batch,
                )
                # Ordena por index para garantir ordem correta
                batch_embeddings = sorted(
                    [item.embedding for item in response.data],
                    key=lambda e: response.data.index(
                        next(x for x in response.data if x.embedding == e)
                    ),
                )
                all_embeddings.extend(batch_embeddings)
                logger.debug(
                    "Batch %d-%d: %d embeddings gerados",
                    i,
                    i + len(batch),
                    len(batch_embeddings),
                )
            except Exception as exc:
                logger.error("Erro ao gerar embeddings batch %d: %s", i, exc)
                raise EmbeddingError(f"Falha ao gerar embeddings: {exc}") from exc

        return all_embeddings

    def _mock_embed(self, texts: list[str]) -> list[list[float]]:
        """Gera embeddings deterministicos mock para desenvolvimento.

        Usa hash do texto para gerar vetor pseudo-aleatorio consistente.
        """
        embeddings: list[list[float]] = []
        for text in texts:
            seed = int(hashlib.md5(text.encode()).hexdigest(), 16) % (2**32)
            rng = random.Random(seed)
            embedding = [rng.gauss(0, 1) for _ in range(EMBEDDING_DIM)]
            # Normaliza para vetor unitario
            norm = sum(v * v for v in embedding) ** 0.5
            if norm > 0:
                embedding = [v / norm for v in embedding]
            embeddings.append(embedding)
        return embeddings


class EmbeddingError(Exception):
    """Erro durante geracao de embeddings."""

    pass
