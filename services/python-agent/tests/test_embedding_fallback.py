"""
Testes unitarios para fallback de embeddings quando provider nao suporta.

Cobertura:
- Provider sem embeddings (Groq) ativa fallback mock automaticamente.
- OpenAI padrao (sem base_url) NAO ativa fallback — erro e propagado.
- Fallback ativa apenas uma vez e persiste na instancia.
- embed_texts com fallback no meio do batch retorna mock para restante.
- _is_provider_without_embeddings reconhece padroes de erro corretos.
- Erros genericos de provider alternativo sao propagados (nao engolidos).
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from app.core.config import Settings
from app.infrastructure.embeddings.openai_embedder import (
    EmbeddingError,
    OpenAIEmbedder,
    _is_provider_without_embeddings,
)


class TestIsProviderWithoutEmbeddings:
    """Testes da funcao de deteccao de provider sem embeddings."""

    def test_notfounderror_is_detected(self) -> None:
        """NotFoundError da SDK OpenAI e reconhecido."""

        class NotFoundError(Exception):
            pass

        exc = NotFoundError("model does not exist")
        assert _is_provider_without_embeddings(exc) is True

    def test_apierror_is_detected(self) -> None:
        """APIError da SDK OpenAI e reconhecido."""

        class APIError(Exception):
            pass

        exc = APIError("endpoint not found")
        assert _is_provider_without_embeddings(exc) is True

    def test_does_not_exist_pattern(self) -> None:
        """Mensagem 'does not exist' e reconhecida."""
        exc = Exception("The model `text-embedding-3-small` does not exist")
        assert _is_provider_without_embeddings(exc) is True

    def test_not_found_pattern(self) -> None:
        """Mensagem 'not found' e reconhecida."""
        exc = Exception("404 Not Found: /v1/embeddings")
        assert _is_provider_without_embeddings(exc) is True

    def test_unsupported_pattern(self) -> None:
        """Mensagem 'unsupported' e reconhecida."""
        exc = Exception("Model unsupported for embeddings")
        assert _is_provider_without_embeddings(exc) is True

    def test_no_endpoint_pattern(self) -> None:
        """Mensagem 'no endpoint' e reconhecida."""
        exc = Exception("No endpoint available for embeddings")
        assert _is_provider_without_embeddings(exc) is True

    def test_404_pattern(self) -> None:
        """Mensagem com '404' e reconhecida."""
        exc = Exception("Error 404: resource not available")
        assert _is_provider_without_embeddings(exc) is True

    def test_generic_error_not_detected(self) -> None:
        """Erro generico de conexao NAO e confundido com falta de embeddings."""
        exc = Exception("Connection timeout after 30s")
        assert _is_provider_without_embeddings(exc) is False

    def test_rate_limit_not_detected(self) -> None:
        """Erro de rate limit NAO ativa fallback de embeddings."""
        exc = Exception("Rate limit exceeded, try again later")
        assert _is_provider_without_embeddings(exc) is False

    def test_authentication_error_not_detected(self) -> None:
        """Erro de autenticacao NAO ativa fallback de embeddings."""
        exc = Exception("Invalid API key provided")
        assert _is_provider_without_embeddings(exc) is False


class TestEmbedderFallbackGroq:
    """Testes de fallback quando provider alternativo nao suporta embeddings."""

    def _make_not_found_error(self) -> Exception:
        """Cria excecao simulando erro de provider sem embeddings."""

        class NotFoundError(Exception):
            pass

        return NotFoundError(
            "The model `text-embedding-3-small` does not exist or you do not have access"
        )

    def test_embed_query_falls_back_to_mock_on_groq_error(self) -> None:
        """embed_query cai para mock quando Groq retorna erro de modelo."""
        settings = Settings(
            OPENAI_API_KEY="gsk_test_key",
            OPENAI_BASE_URL="https://api.groq.com/openai/v1",
            EMBEDDING_MODEL="text-embedding-3-small",
        )

        with patch("openai.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_client.embeddings.create.side_effect = self._make_not_found_error()
            mock_openai.return_value = mock_client

            embedder = OpenAIEmbedder(settings)

            # Primeira chamada: deve cair para mock
            result = embedder.embed_query("test query")

            assert isinstance(result, list)
            assert len(result) == 1536
            assert embedder._fallback_active is True

    def test_embed_query_fallback_persists(self) -> None:
        """Apos fallback ativado, chamadas seguintes usam mock direto."""
        settings = Settings(
            OPENAI_API_KEY="gsk_test_key",
            OPENAI_BASE_URL="https://api.groq.com/openai/v1",
            EMBEDDING_MODEL="text-embedding-3-small",
        )

        with patch("openai.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_client.embeddings.create.side_effect = self._make_not_found_error()
            mock_openai.return_value = mock_client

            embedder = OpenAIEmbedder(settings)

            # Primeira chamada ativa fallback
            result1 = embedder.embed_query("query 1")
            assert embedder._fallback_active is True

            # Reseta side_effect para verificar que nao chama mais a API
            mock_client.embeddings.create.reset_mock()
            mock_client.embeddings.create.side_effect = None

            # Segunda chamada usa mock direto (sem chamar API)
            result2 = embedder.embed_query("query 2")

            assert isinstance(result2, list)
            assert len(result2) == 1536
            # API nao deve ter sido chamada novamente
            mock_client.embeddings.create.assert_not_called()

    def test_embed_texts_falls_back_mid_batch(self) -> None:
        """embed_texts cai para mock no meio do batch e retorna resto como mock."""
        settings = Settings(
            OPENAI_API_KEY="gsk_test_key",
            OPENAI_BASE_URL="https://api.groq.com/openai/v1",
            EMBEDDING_MODEL="text-embedding-3-small",
        )

        with patch("openai.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_client.embeddings.create.side_effect = self._make_not_found_error()
            mock_openai.return_value = mock_client

            embedder = OpenAIEmbedder(settings)

            texts = ["text1", "text2", "text3"]
            result = embedder.embed_texts(texts, batch_size=2)

            assert isinstance(result, list)
            assert len(result) == 3
            assert all(isinstance(e, list) and len(e) == 1536 for e in result)
            assert embedder._fallback_active is True

    def test_fallback_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Ativacao de fallback gera warning estruturado."""
        settings = Settings(
            OPENAI_API_KEY="gsk_test_key",
            OPENAI_BASE_URL="https://api.groq.com/openai/v1",
            EMBEDDING_MODEL="text-embedding-3-small",
        )

        with patch("openai.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_client.embeddings.create.side_effect = self._make_not_found_error()
            mock_openai.return_value = mock_client

            with caplog.at_level(logging.WARNING):
                embedder = OpenAIEmbedder(settings)
                embedder.embed_query("test")

            assert any(
                "nao suporta embeddings" in record.message.lower()
                for record in caplog.records
            )
            assert any(
                "fallback mock" in record.message.lower()
                for record in caplog.records
            )


class TestEmbedderNoFallbackForOpenAI:
    """Testes que garantem que OpenAI padrao NAO ativa fallback indiscriminado."""

    def test_openai_standard_propagates_error(self) -> None:
        """OpenAI padrao (sem base_url) propaga erro em vez de fallback."""
        settings = Settings(
            OPENAI_API_KEY="sk_test_key",
            OPENAI_BASE_URL="",
            EMBEDDING_MODEL="text-embedding-3-small",
        )

        with patch("openai.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_client.embeddings.create.side_effect = Exception("API error")
            mock_openai.return_value = mock_client

            embedder = OpenAIEmbedder(settings)

            with pytest.raises(EmbeddingError, match="Falha ao gerar embedding"):
                embedder.embed_query("test query")

            assert embedder._fallback_active is False

    def test_openai_standard_rate_limit_propagates(self) -> None:
        """Rate limit em OpenAI padrao NAO ativa fallback."""
        settings = Settings(
            OPENAI_API_KEY="sk_test_key",
            OPENAI_BASE_URL="",
            EMBEDDING_MODEL="text-embedding-3-small",
        )

        with patch("openai.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_client.embeddings.create.side_effect = Exception(
                "Rate limit exceeded"
            )
            mock_openai.return_value = mock_client

            embedder = OpenAIEmbedder(settings)

            with pytest.raises(EmbeddingError):
                embedder.embed_query("test query")

            assert embedder._fallback_active is False

    def test_alternative_provider_generic_error_propagates(self) -> None:
        """Erro generico (nao relacionado a embeddings) em provider alternativo e propagado."""
        settings = Settings(
            OPENAI_API_KEY="test_key",
            OPENAI_BASE_URL="https://api.alternative.com/v1",
            EMBEDDING_MODEL="text-embedding-3-small",
        )

        with patch("openai.OpenAI") as mock_openai:
            mock_client = MagicMock()
            # Erro de conexao/timeout nao deve ativar fallback
            mock_client.embeddings.create.side_effect = Exception(
                "Connection timeout after 30s"
            )
            mock_openai.return_value = mock_client

            embedder = OpenAIEmbedder(settings)

            with pytest.raises(EmbeddingError, match="Falha ao gerar embedding"):
                embedder.embed_query("test query")

            assert embedder._fallback_active is False


class TestEmbedderMockModeUnchanged:
    """Testes que garantem que modo mock original (sem API key) funciona como antes."""

    def test_no_api_key_uses_mock(self) -> None:
        """Sem OPENAI_API_KEY, usa mock diretamente."""
        settings = Settings(
            OPENAI_API_KEY="",
            OPENAI_BASE_URL="",
        )

        embedder = OpenAIEmbedder(settings)

        assert embedder._use_mock is True
        assert embedder._fallback_active is False

        result = embedder.embed_query("test")
        assert isinstance(result, list)
        assert len(result) == 1536

    def test_mock_deterministic(self) -> None:
        """Embeddings mock sao deterministicos para mesmo texto."""
        settings = Settings(OPENAI_API_KEY="")

        embedder = OpenAIEmbedder(settings)

        result1 = embedder.embed_query("same text")
        result2 = embedder.embed_query("same text")

        assert result1 == result2

    def test_mock_different_texts(self) -> None:
        """Embeddings mock sao diferentes para textos diferentes."""
        settings = Settings(OPENAI_API_KEY="")

        embedder = OpenAIEmbedder(settings)

        result1 = embedder.embed_query("text A")
        result2 = embedder.embed_query("text B")

        assert result1 != result2
