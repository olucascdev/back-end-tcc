"""
Gerador de embeddings via OpenAI API.

Usa modelo text-embedding-3-small. Inclui fallback mock para:
- Desenvolvimento quando OPENAI_API_KEY nao esta configurada.
- Providers OpenAI-compatíveis que nao suportam embeddings (ex: Groq).
"""

from __future__ import annotations

import logging
import hashlib
import random

from app.core.config import Settings

logger = logging.getLogger(__name__)

# Dimensao padrao do modelo text-embedding-3-small
EMBEDDING_DIM = 1536

# Mensagens de erro tipicas de provider sem suporte a embeddings
_NO_EMBEDDING_PATTERNS = (
    "does not exist",
    "not found",
    "unsupported",
    "no endpoint",
    "404",
)


def _is_provider_without_embeddings(error: Exception) -> bool:
    """Verifica se o erro indica que o provider nao suporta embeddings.

    Analisa o tipo e a mensagem do erro para determinar se se trata
    de um provider OpenAI-compativel sem endpoint de embeddings
    (caso tipico do Groq).

    Args:
        error: excecao capturada durante chamada de embeddings.

    Returns:
        True se o erro corresponde a provider sem embeddings.
    """
    error_msg = str(error).lower()

    # Verifica por tipo de excecao da SDK OpenAI
    error_type = type(error).__name__.lower()
    if error_type in ("notfounderror", "apierror"):
        return True

    # Verifica por padroes conhecidos na mensagem de erro
    return any(pattern in error_msg for pattern in _NO_EMBEDDING_PATTERNS)


class OpenAIEmbedder:
    """Gera embeddings de texto usando OpenAI ou fallback mock."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or Settings()
        self._use_mock = not self._settings.OPENAI_API_KEY
        # Flag para indicar se ja ocorreu fallback por provider sem embeddings
        self._fallback_active = False

        if self._use_mock:
            logger.warning(
                "OPENAI_API_KEY nao configurada; usando embeddings mock para desenvolvimento."
            )
        else:
            from openai import OpenAI

            # Usa base_url se configurado (ex: Groq ou outro provider compativel)
            base_url = self._settings.OPENAI_BASE_URL or None
            self._client = OpenAI(
                api_key=self._settings.OPENAI_API_KEY,
                base_url=base_url,
            )
            self._model = self._settings.EMBEDDING_MODEL

    def _should_fallback_to_mock(self, exc: Exception) -> bool:
        """Determina se deve cair para mock com base no erro e configuracao.

        O fallback so e ativado quando:
        - OPENAI_BASE_URL esta configurado (provider alternativo).
        - O erro indica que o provider nao suporta embeddings.

        Para OpenAI padrao (base_url vazio), qualquer erro e propagado.

        Args:
            exc: excecao capturada durante chamada de embeddings.

        Returns:
            True se deve usar fallback mock.
        """
        # Sem base_url configurado = OpenAI padrao, nao faz fallback
        if not self._settings.OPENAI_BASE_URL:
            return False

        return _is_provider_without_embeddings(exc)

    def _activate_fallback(self) -> None:
        """Ativa modo fallback mock permanentemente para esta instancia."""
        if not self._fallback_active:
            self._fallback_active = True
            logger.warning(
                "Provider configurado via OPENAI_BASE_URL nao suporta embeddings. "
                "Ativando fallback mock para embeddings. "
                "Para embeddings reais, use a API OpenAI padrao ou um provider compativel."
            )

    def embed_query(self, text: str) -> list[float]:
        """Gera embedding para uma unica string de consulta.

        Args:
            text: texto da pergunta ou consulta.

        Returns:
            Embedding como list[float].
        """
        if self._use_mock or self._fallback_active:
            return self._mock_embed([text])[0]

        try:
            response = self._client.embeddings.create(
                model=self._model,
                input=text,
            )
            return response.data[0].embedding
        except Exception as exc:
            if self._should_fallback_to_mock(exc):
                self._activate_fallback()
                return self._mock_embed([text])[0]

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
        if self._use_mock or self._fallback_active:
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
                if self._should_fallback_to_mock(exc):
                    self._activate_fallback()
                    # Retorna mock para o batch atual e todos os restantes
                    remaining = texts[i:]
                    all_embeddings.extend(self._mock_embed(remaining))
                    return all_embeddings

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
