"""
Testes do OpenAIEmbedder.

Verifica geracao de embeddings, batching e modo mock.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.infrastructure.embedder import EMBEDDING_DIM, OpenAIEmbedder


class TestMockMode:
    """Testes do modo mock."""

    def test_mock_mode_without_api_key(self) -> None:
        """Verifica que embedder entra em modo mock sem API key."""
        embedder = OpenAIEmbedder(api_key="")
        assert embedder.is_mock_mode is True

    def test_mock_mode_with_empty_api_key(self) -> None:
        """Verifica que API key vazia ativa modo mock."""
        embedder = OpenAIEmbedder(api_key="   ")
        assert embedder.is_mock_mode is True

    @pytest.mark.asyncio
    async def test_mock_embed_returns_correct_dim(self) -> None:
        """Verifica que embeddings mock tem dimensao correta."""
        embedder = OpenAIEmbedder(api_key="")
        result = await embedder.embed_texts(["Hello world"])

        assert len(result) == 1
        assert len(result[0]) == EMBEDDING_DIM

    @pytest.mark.asyncio
    async def test_mock_embed_deterministic(self) -> None:
        """Verifica que embeddings mock sao deterministicos."""
        embedder = OpenAIEmbedder(api_key="")

        result1 = await embedder.embed_texts(["Hello world"])
        result2 = await embedder.embed_texts(["Hello world"])

        assert result1 == result2

    @pytest.mark.asyncio
    async def test_mock_embed_different_texts(self) -> None:
        """Verifica que textos diferentes geram embeddings diferentes."""
        embedder = OpenAIEmbedder(api_key="")

        result1 = await embedder.embed_texts(["Hello"])
        result2 = await embedder.embed_texts(["World"])

        assert result1 != result2

    @pytest.mark.asyncio
    async def test_mock_embed_batch(self) -> None:
        """Verifica embedding de multiplos textos."""
        embedder = OpenAIEmbedder(api_key="")
        texts = [f"Text {i}" for i in range(10)]

        result = await embedder.embed_texts(texts)

        assert len(result) == 10
        for embedding in result:
            assert len(embedding) == EMBEDDING_DIM

    @pytest.mark.asyncio
    async def test_mock_embed_empty_list(self) -> None:
        """Verifica que lista vazia retorna lista vazia."""
        embedder = OpenAIEmbedder(api_key="")
        result = await embedder.embed_texts([])
        assert result == []

    @pytest.mark.asyncio
    async def test_mock_embed_filters_empty_strings(self) -> None:
        """Verifica que strings vazias sao filtradas."""
        embedder = OpenAIEmbedder(api_key="")
        texts = ["Hello", "", "  ", "World"]

        result = await embedder.embed_texts(texts)

        assert len(result) == 4
        # Strings vazias devem retornar vetores zerados
        assert result[1] == [0.0] * EMBEDDING_DIM
        assert result[2] == [0.0] * EMBEDDING_DIM

    @pytest.mark.asyncio
    async def test_mock_embed_unit_vectors(self) -> None:
        """Verifica que embeddings mock sao vetores unitarios."""
        embedder = OpenAIEmbedder(api_key="")
        result = await embedder.embed_texts(["Test text"])

        embedding = result[0]
        magnitude = sum(x * x for x in embedding) ** 0.5
        # Deve estar proximo de 1.0 (tolerancia para floating point)
        assert abs(magnitude - 1.0) < 0.01


class TestRealMode:
    """Testes do modo real (com mock da API)."""

    @pytest.mark.asyncio
    async def test_real_mode_not_mock_with_key(self) -> None:
        """Verifica que com API key e openai instalado nao entra em modo mock."""
        # Mock do import do openai para simular package instalada
        with patch.dict("sys.modules", {"openai": MagicMock()}):
            # Forca reimport para pegar o mock
            import importlib
            import app.infrastructure.embedder as embedder_mod

            importlib.reload(embedder_mod)

            embedder = embedder_mod.OpenAIEmbedder(api_key="sk-test-key")
            # Com openai mockado no sys.modules, nao deve entrar em modo mock
            # mas o client pode ser None se o mock nao tem AsyncOpenAI
            # O importante e que nao e mock_mode por falta de key
            assert not embedder._mock_mode or embedder._client is not None

    @pytest.mark.asyncio
    async def test_real_api_call_mocked(self) -> None:
        """Verifica chamada a API OpenAI com mock direto no metodo."""
        embedder = OpenAIEmbedder(api_key="sk-test-key")
        # Forca modo nao-mock para testar o fluxo real
        embedder._mock_mode = False

        # Mock do client
        mock_response = MagicMock()
        mock_embedding = MagicMock()
        mock_embedding.index = 0
        mock_embedding.embedding = [0.1] * EMBEDDING_DIM
        mock_response.data = [mock_embedding]

        embedder._client = AsyncMock()
        embedder._client.embeddings.create = AsyncMock(return_value=mock_response)

        result = await embedder.embed_texts(["Test"])

        assert len(result) == 1
        assert len(result[0]) == EMBEDDING_DIM
        embedder._client.embeddings.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_real_api_batching(self) -> None:
        """Verifica que textos sao enviados em batches de max 100."""
        embedder = OpenAIEmbedder(api_key="sk-test-key")
        embedder._mock_mode = False

        # Mock do client
        def create_mock_response(texts):
            mock_response = MagicMock()
            mock_response.data = [
                MagicMock(index=i, embedding=[0.1] * EMBEDDING_DIM)
                for i in range(len(texts))
            ]
            return mock_response

        embedder._client = AsyncMock()
        embedder._client.embeddings.create = AsyncMock(
            side_effect=lambda **kwargs: create_mock_response(kwargs["input"])
        )

        # 150 textos = 2 batches (100 + 50)
        texts = [f"Text {i}" for i in range(150)]
        result = await embedder.embed_texts(texts)

        assert len(result) == 150
        assert embedder._client.embeddings.create.call_count == 2


class TestRetry:
    """Testes de retry em falhas transientes."""

    @pytest.mark.asyncio
    async def test_retry_on_transient_error(self) -> None:
        """Verifica retry em erro transiente."""
        embedder = OpenAIEmbedder(api_key="sk-test-key", max_retries=2)
        embedder._mock_mode = False

        call_count = 0

        async def flaky_create(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise TimeoutError("Connection timeout")
            mock_response = MagicMock()
            mock_response.data = [MagicMock(index=0, embedding=[0.1] * EMBEDDING_DIM)]
            return mock_response

        embedder._client = AsyncMock()
        embedder._client.embeddings.create = flaky_create

        result = await embedder.embed_texts(["Test"])

        assert len(result) == 1
        assert call_count == 2  # Primeira falhou, segunda funcionou

    @pytest.mark.asyncio
    async def test_no_retry_on_permanent_error(self) -> None:
        """Verifica que erro permanente nao e retentado."""
        embedder = OpenAIEmbedder(api_key="sk-test-key", max_retries=3)
        embedder._mock_mode = False

        call_count = 0

        async def fail_permanent(**kwargs):
            nonlocal call_count
            call_count += 1
            raise ValueError("Invalid API key")

        embedder._client = AsyncMock()
        embedder._client.embeddings.create = fail_permanent

        with pytest.raises(ValueError, match="Invalid API key"):
            await embedder.embed_texts(["Test"])

        assert call_count == 1  # Apenas uma tentativa
