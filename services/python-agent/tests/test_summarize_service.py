"""
Testes unitarios do SummarizeService.

Cobertura:
- Resumo com contexto suficiente (mocks de embedder, vector_store, LLM).
- Fallback quando contexto insuficiente (vector_store retorna vazio).
- Parsing quando LLM retorna estrutura incompleta.
- Isolamento por project_id/document_id.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.domain.summarize_service import (
    INSUFFICIENT_CONTEXT,
    NOT_IDENTIFIED,
    SUMMARIZE_QUERY,
    SummarizeError,
    SummarizeService,
)
from app.schemas.contracts_v1 import SummarizeResponse


def _make_chunk(
    content: str,
    project_id: str,
    document_id: str,
    page: int = 1,
    score: float = 0.85,
) -> dict:
    """Helper para criar chunk mock."""
    return {
        "content": content,
        "metadata": {
            "project_id": project_id,
            "document_id": document_id,
            "page_number": page,
            "chunk_index": 0,
        },
        "score": score,
    }


class TestSummarizeServiceWithContext:
    """Testes de resumo com contexto suficiente."""

    def test_summarize_returns_structured_summary(self) -> None:
        """Verifica resumo completo com 4 chaves quando ha contexto."""
        project_id = str(uuid4())
        document_id = str(uuid4())

        # Mocks
        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder._use_mock = True

        mock_vector_store = MagicMock()
        mock_vector_store.search_similar_by_project.return_value = [
            _make_chunk(
                content="Este estudo investiga o impacto de IA na educacao superior.",
                project_id=project_id,
                document_id=document_id,
            ),
            _make_chunk(
                content="A metodologia utilizou survey com 500 estudantes.",
                project_id=project_id,
                document_id=document_id,
            ),
        ]

        service = SummarizeService(
            embedder=mock_embedder,
            vector_store=mock_vector_store,
        )

        result = service.summarize(project_id=project_id, document_id=document_id)

        # Verifica estrutura
        assert isinstance(result, SummarizeResponse)
        assert str(result.document_id) == document_id
        assert "objective" in result.summary
        assert "methodology" in result.summary
        assert "results" in result.summary
        assert "conclusion" in result.summary

        # Verifica que embedder foi chamado com query fixa
        mock_embedder.embed_query.assert_called_once_with(SUMMARIZE_QUERY)

        # Verifica que vector_store foi chamado com parametros corretos
        mock_vector_store.search_similar_by_project.assert_called_once_with(
            project_id=project_id,
            query_embedding=[0.1] * 1536,
            top_k=10,
            min_score=0.5,
        )

    def test_summarize_filters_by_document_id(self) -> None:
        """Verifica que chunks de outros documentos sao filtrados."""
        project_id = str(uuid4())
        target_doc = str(uuid4())
        other_doc = str(uuid4())

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder._use_mock = True

        mock_vector_store = MagicMock()
        # Retorna chunks de documentos diferentes
        mock_vector_store.search_similar_by_project.return_value = [
            _make_chunk(
                content="Conteudo do documento alvo.",
                project_id=project_id,
                document_id=target_doc,
            ),
            _make_chunk(
                content="Conteudo de outro documento.",
                project_id=project_id,
                document_id=other_doc,
            ),
        ]

        service = SummarizeService(
            embedder=mock_embedder,
            vector_store=mock_vector_store,
        )

        result = service.summarize(project_id=project_id, document_id=target_doc)

        # Deve usar apenas o chunk do documento alvo
        assert result.summary["objective"] != INSUFFICIENT_CONTEXT


class TestSummarizeServiceInsufficientContext:
    """Testes de fallback quando contexto insuficiente."""

    def test_summarize_returns_insufficient_when_no_chunks(self) -> None:
        """Verifica fallback quando vector_store retorna lista vazia."""
        project_id = str(uuid4())
        document_id = str(uuid4())

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder._use_mock = True

        mock_vector_store = MagicMock()
        mock_vector_store.search_similar_by_project.return_value = []

        service = SummarizeService(
            embedder=mock_embedder,
            vector_store=mock_vector_store,
        )

        result = service.summarize(project_id=project_id, document_id=document_id)

        assert result.summary["objective"] == INSUFFICIENT_CONTEXT
        assert result.summary["methodology"] == INSUFFICIENT_CONTEXT
        assert result.summary["results"] == INSUFFICIENT_CONTEXT
        assert result.summary["conclusion"] == INSUFFICIENT_CONTEXT

    def test_summarize_returns_insufficient_when_no_matching_document(self) -> None:
        """Verifica fallback quando chunks existem mas sao de outro documento."""
        project_id = str(uuid4())
        target_doc = str(uuid4())
        other_doc = str(uuid4())

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder._use_mock = True

        mock_vector_store = MagicMock()
        # Todos os chunks sao de outro documento
        mock_vector_store.search_similar_by_project.return_value = [
            _make_chunk(
                content="Conteudo irrelevante.",
                project_id=project_id,
                document_id=other_doc,
            ),
        ]

        service = SummarizeService(
            embedder=mock_embedder,
            vector_store=mock_vector_store,
        )

        result = service.summarize(project_id=project_id, document_id=target_doc)

        assert result.summary["objective"] == INSUFFICIENT_CONTEXT


class TestSummarizeServiceParsing:
    """Testes de parsing da resposta do LLM."""

    def test_parse_complete_json_response(self) -> None:
        """Verifica parsing de resposta JSON completa."""
        project_id = str(uuid4())
        document_id = str(uuid4())

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder._use_mock = True

        mock_vector_store = MagicMock()
        mock_vector_store.search_similar_by_project.return_value = [
            _make_chunk("Conteudo teste", project_id, document_id),
        ]

        service = SummarizeService(
            embedder=mock_embedder,
            vector_store=mock_vector_store,
        )

        # Mock do _call_llm para retornar JSON valido completo
        with patch.object(service, "_call_llm") as mock_llm:
            mock_llm.return_value = (
                '{"objective": "Obj X", "methodology": "Met Y", '
                '"results": "Res Z", "conclusion": "Con W"}'
            )
            result = service.summarize(
                project_id=project_id,
                document_id=document_id,
            )

        assert result.summary["objective"] == "Obj X"
        assert result.summary["methodology"] == "Met Y"
        assert result.summary["results"] == "Res Z"
        assert result.summary["conclusion"] == "Con W"

    def test_parse_incomplete_json_response(self) -> None:
        """Verifica que chaves ausentes sao preenchidas com 'Nao identificado'."""
        project_id = str(uuid4())
        document_id = str(uuid4())

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder._use_mock = True

        mock_vector_store = MagicMock()
        mock_vector_store.search_similar_by_project.return_value = [
            _make_chunk("Conteudo teste", project_id, document_id),
        ]

        service = SummarizeService(
            embedder=mock_embedder,
            vector_store=mock_vector_store,
        )

        # LLM retorna apenas 2 das 4 chaves
        with patch.object(service, "_call_llm") as mock_llm:
            mock_llm.return_value = '{"objective": "Obj X", "results": "Res Z"}'
            result = service.summarize(
                project_id=project_id,
                document_id=document_id,
            )

        assert result.summary["objective"] == "Obj X"
        assert result.summary["methodology"] == NOT_IDENTIFIED
        assert result.summary["results"] == "Res Z"
        assert result.summary["conclusion"] == NOT_IDENTIFIED

    def test_parse_markdown_code_block_response(self) -> None:
        """Verifica parsing de resposta com code block markdown."""
        project_id = str(uuid4())
        document_id = str(uuid4())

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder._use_mock = True

        mock_vector_store = MagicMock()
        mock_vector_store.search_similar_by_project.return_value = [
            _make_chunk("Conteudo teste", project_id, document_id),
        ]

        service = SummarizeService(
            embedder=mock_embedder,
            vector_store=mock_vector_store,
        )

        # LLM retorna JSON dentro de code block
        with patch.object(service, "_call_llm") as mock_llm:
            mock_llm.return_value = (
                "```json\n"
                '{"objective": "Obj A", "methodology": "Met B", '
                '"results": "Res C", "conclusion": "Con D"}\n'
                "```"
            )
            result = service.summarize(
                project_id=project_id,
                document_id=document_id,
            )

        assert result.summary["objective"] == "Obj A"
        assert result.summary["methodology"] == "Met B"
        assert result.summary["results"] == "Res C"
        assert result.summary["conclusion"] == "Con D"

    def test_parse_invalid_json_response(self) -> None:
        """Verifica fallback quando LLM retorna texto invalido."""
        project_id = str(uuid4())
        document_id = str(uuid4())

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder._use_mock = True

        mock_vector_store = MagicMock()
        mock_vector_store.search_similar_by_project.return_value = [
            _make_chunk("Conteudo teste", project_id, document_id),
        ]

        service = SummarizeService(
            embedder=mock_embedder,
            vector_store=mock_vector_store,
        )

        # LLM retorna texto nao-JSON
        with patch.object(service, "_call_llm") as mock_llm:
            mock_llm.return_value = "Este e um texto sem estrutura JSON."
            result = service.summarize(
                project_id=project_id,
                document_id=document_id,
            )

        # Todas as chaves devem ter valor padrao
        assert result.summary["objective"] == NOT_IDENTIFIED
        assert result.summary["methodology"] == NOT_IDENTIFIED
        assert result.summary["results"] == NOT_IDENTIFIED
        assert result.summary["conclusion"] == NOT_IDENTIFIED


class TestSummarizeServiceIsolation:
    """Testes de isolamento por project_id/document_id."""

    def test_isolation_by_project_id(self) -> None:
        """Verifica que busca usa project_id correto."""
        project_a = str(uuid4())
        project_b = str(uuid4())
        document_id = str(uuid4())

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder._use_mock = True

        mock_vector_store = MagicMock()
        mock_vector_store.search_similar_by_project.return_value = []

        service = SummarizeService(
            embedder=mock_embedder,
            vector_store=mock_vector_store,
        )

        service.summarize(project_id=project_a, document_id=document_id)

        # Verifica que a busca foi feita com project_a
        call_kwargs = mock_vector_store.search_similar_by_project.call_args[1]
        assert call_kwargs["project_id"] == project_a

    def test_isolation_by_document_id(self) -> None:
        """Verifica que filtro por document_id isola chunks corretamente."""
        project_id = str(uuid4())
        doc_a = str(uuid4())
        doc_b = str(uuid4())

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder._use_mock = True

        mock_vector_store = MagicMock()
        # Retorna chunks de ambos documentos
        mock_vector_store.search_similar_by_project.return_value = [
            _make_chunk("Conteudo doc A", project_id, doc_a),
            _make_chunk("Conteudo doc B", project_id, doc_b),
        ]

        service = SummarizeService(
            embedder=mock_embedder,
            vector_store=mock_vector_store,
        )

        # Resumo de doc_a deve usar apenas chunk de doc_a
        result_a = service.summarize(project_id=project_id, document_id=doc_a)
        assert result_a.summary["objective"] != INSUFFICIENT_CONTEXT

        # Resumo de doc_b deve usar apenas chunk de doc_b
        result_b = service.summarize(project_id=project_id, document_id=doc_b)
        assert result_b.summary["objective"] != INSUFFICIENT_CONTEXT
