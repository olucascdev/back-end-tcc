"""
Testes unitarios para configuracao de LLM provider (OPENAI_BASE_URL).

Cobertura:
- Settings carrega OPENAI_BASE_URL corretamente.
- OpenAIEmbedder usa base_url quando configurado.
- Servicos de dominio passam base_url ao cliente OpenAI.
- Comportamento padrao (base_url vazio = None) nao quebra OpenAI original.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.core.config import Settings


class TestSettingsOpenAIBaseUrl:
    """Testes de carregamento de OPENAI_BASE_URL nas Settings."""

    def test_default_base_url_is_empty_string(self) -> None:
        """Verifica que o valor padrao de OPENAI_BASE_URL e string vazia."""
        settings = Settings()
        assert settings.OPENAI_BASE_URL == ""

    def test_base_url_from_env_variable(self) -> None:
        """Verifica que OPENAI_BASE_URL pode ser configurado via ambiente."""
        settings = Settings(OPENAI_BASE_URL="https://api.groq.com/openai/v1")
        assert settings.OPENAI_BASE_URL == "https://api.groq.com/openai/v1"

    def test_base_url_empty_string_is_falsy_for_logic(self) -> None:
        """Verifica que string vazia e tratada como 'nao configurado'."""
        settings = Settings(OPENAI_BASE_URL="")
        base_url = settings.OPENAI_BASE_URL or None
        assert base_url is None


class TestOpenAIEmbedderBaseUrl:
    """Testes de que OpenAIEmbedder respeita OPENAI_BASE_URL."""

    def test_embedder_uses_base_url_when_configured(self) -> None:
        """Verifica que embedder passa base_url ao cliente OpenAI."""
        settings = Settings(
            OPENAI_API_KEY="test-key",
            OPENAI_BASE_URL="https://api.groq.com/openai/v1",
            EMBEDDING_MODEL="text-embedding-3-small",
        )

        # OpenAI e importado lazy dentro do metodo, patch no modulo openai
        with patch("openai.OpenAI") as mock_openai:
            from app.infrastructure.embeddings.openai_embedder import OpenAIEmbedder

            OpenAIEmbedder(settings)

            mock_openai.assert_called_once_with(
                api_key="test-key",
                base_url="https://api.groq.com/openai/v1",
            )

    def test_embedder_passes_none_base_url_when_empty(self) -> None:
        """Verifica que embedder passa base_url=None quando nao configurado."""
        settings = Settings(
            OPENAI_API_KEY="test-key",
            OPENAI_BASE_URL="",
            EMBEDDING_MODEL="text-embedding-3-small",
        )

        with patch("openai.OpenAI") as mock_openai:
            from app.infrastructure.embeddings.openai_embedder import OpenAIEmbedder

            OpenAIEmbedder(settings)

            mock_openai.assert_called_once_with(
                api_key="test-key",
                base_url=None,
            )


class TestDomainServicesBaseUrl:
    """Testes de que servicos de dominio respeitam OPENAI_BASE_URL."""

    def _make_chunk(self, content: str, project_id: str, document_id: str) -> dict:
        return {
            "content": content,
            "metadata": {
                "project_id": project_id,
                "document_id": document_id,
                "page_number": 1,
                "chunk_index": 0,
            },
            "score": 0.85,
        }

    def test_rag_service_passes_base_url_to_openai(self) -> None:
        """Verifica que RAGService passa base_url ao chamar LLM."""
        from app.domain.rag_service import RAGService

        settings = Settings(
            OPENAI_API_KEY="test-key",
            OPENAI_BASE_URL="https://api.groq.com/openai/v1",
            OPENAI_MODEL="llama-3.3-70b-versatile",
        )
        mock_embedder = MagicMock()
        mock_embedder._use_mock = False
        mock_vector_store = MagicMock()

        service = RAGService(
            settings=settings,
            embedder=mock_embedder,
            vector_store=mock_vector_store,
        )

        # _call_llm chama conversation_repository.get_conversation_history
        # que tenta conectar ao banco; precisamos mockar isso tambem
        with (
            patch("app.domain.rag_service.conversation_repository") as mock_repo,
            patch("openai.OpenAI") as mock_openai,
        ):
            mock_repo.get_conversation_history.return_value = []
            mock_openai.return_value.chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content="test response"))]
            )

            service._call_llm(context="test context", question="test?", session_id="s1")

            mock_openai.assert_called_once_with(
                api_key="test-key",
                base_url="https://api.groq.com/openai/v1",
            )

    def test_summarize_service_passes_base_url_to_openai(self) -> None:
        """Verifica que SummarizeService passa base_url ao chamar LLM."""
        from app.domain.summarize_service import SummarizeService

        settings = Settings(
            OPENAI_API_KEY="test-key",
            OPENAI_BASE_URL="https://api.groq.com/openai/v1",
            OPENAI_MODEL="llama-3.3-70b-versatile",
        )
        mock_embedder = MagicMock()
        mock_embedder._use_mock = False
        mock_vector_store = MagicMock()

        service = SummarizeService(
            settings=settings,
            embedder=mock_embedder,
            vector_store=mock_vector_store,
        )

        with patch("openai.OpenAI") as mock_openai:
            mock_openai.return_value.chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content='{"objective":"test"}'))]
            )

            service._call_llm(context="test context")

            mock_openai.assert_called_once_with(
                api_key="test-key",
                base_url="https://api.groq.com/openai/v1",
            )

    def test_compare_service_passes_base_url_to_openai(self) -> None:
        """Verifica que CompareService passa base_url ao chamar LLM."""
        from app.domain.compare_service import CompareService

        settings = Settings(
            OPENAI_API_KEY="test-key",
            OPENAI_BASE_URL="https://api.groq.com/openai/v1",
            OPENAI_MODEL="llama-3.3-70b-versatile",
        )
        mock_embedder = MagicMock()
        mock_embedder._use_mock = False
        mock_vector_store = MagicMock()

        service = CompareService(
            settings=settings,
            embedder=mock_embedder,
            vector_store=mock_vector_store,
        )

        with patch("openai.OpenAI") as mock_openai:
            mock_openai.return_value.chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content='{"similarities":"test"}'))]
            )

            service._call_llm(context="test context", theme="test theme")

            mock_openai.assert_called_once_with(
                api_key="test-key",
                base_url="https://api.groq.com/openai/v1",
            )

    def test_research_gap_service_passes_base_url_to_openai(self) -> None:
        """Verifica que ResearchGapService passa base_url ao chamar LLM."""
        from app.domain.research_gap_service import ResearchGapService

        settings = Settings(
            OPENAI_API_KEY="test-key",
            OPENAI_BASE_URL="https://api.groq.com/openai/v1",
            OPENAI_MODEL="llama-3.3-70b-versatile",
        )
        mock_embedder = MagicMock()
        mock_embedder._use_mock = False
        mock_vector_store = MagicMock()

        service = ResearchGapService(
            settings=settings,
            embedder=mock_embedder,
            vector_store=mock_vector_store,
        )

        with patch("openai.OpenAI") as mock_openai:
            mock_openai.return_value.chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content="[]"))]
            )

            service._call_llm(context="test context")

            mock_openai.assert_called_once_with(
                api_key="test-key",
                base_url="https://api.groq.com/openai/v1",
            )

    def test_services_use_none_base_url_when_empty(self) -> None:
        """Verifica que servicos passam base_url=None quando nao configurado."""
        from app.domain.summarize_service import SummarizeService

        settings = Settings(
            OPENAI_API_KEY="test-key",
            OPENAI_BASE_URL="",
            OPENAI_MODEL="gpt-4o-mini",
        )
        mock_embedder = MagicMock()
        mock_embedder._use_mock = False
        mock_vector_store = MagicMock()

        service = SummarizeService(
            settings=settings,
            embedder=mock_embedder,
            vector_store=mock_vector_store,
        )

        with patch("openai.OpenAI") as mock_openai:
            mock_openai.return_value.chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content='{"objective":"test"}'))]
            )

            service._call_llm(context="test context")

            mock_openai.assert_called_once_with(
                api_key="test-key",
                base_url=None,
            )
