"""
Testes unitarios do CompareService.

Cobertura:
- Comparacao com contexto suficiente (mocks de embedder, vector_store, LLM).
- Fallback quando contexto insuficiente (vector_store retorna vazio ou < 2 docs).
- Parsing quando LLM retorna formato incompleto.
- Isolamento por project_id.
- Agrupamento correto por document_id.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.domain.compare_service import (
    INSUFFICIENT_CONTEXT,
    CompareError,
    CompareService,
)
from app.schemas.contracts_v1 import CompareResponse, Source


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


class TestCompareServiceWithContext:
    """Testes de comparacao com contexto suficiente."""

    def test_compare_returns_comparison_with_sources(self) -> None:
        """Verifica comparacao completa com 3 chaves e sources quando ha contexto."""
        project_id = str(uuid4())
        doc_a = str(uuid4())
        doc_b = str(uuid4())
        theme = "metodologia de pesquisa"

        # Mocks
        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder._use_mock = True

        mock_vector_store = MagicMock()
        mock_vector_store.search_similar_by_project.return_value = [
            _make_chunk(
                content="Este estudo utiliza abordagem qualitativa.",
                project_id=project_id,
                document_id=doc_a,
                page=1,
                score=0.92,
            ),
            _make_chunk(
                content="A pesquisa foi realizada com entrevistas semiestruturadas.",
                project_id=project_id,
                document_id=doc_a,
                page=3,
                score=0.88,
            ),
            _make_chunk(
                content="Metodologia quantitativa com survey online.",
                project_id=project_id,
                document_id=doc_b,
                page=2,
                score=0.85,
            ),
        ]

        service = CompareService(
            embedder=mock_embedder,
            vector_store=mock_vector_store,
        )

        result = service.compare(
            project_id=project_id,
            document_ids=[doc_a, doc_b],
            theme=theme,
        )

        # Verifica estrutura
        assert isinstance(result, CompareResponse)
        assert str(result.project_id) == project_id
        assert "similarities" in result.comparison
        assert "differences" in result.comparison
        assert "synthesis" in result.comparison
        assert result.comparison["theme"] == theme

        # Verifica sources
        assert len(result.sources) == 3
        assert isinstance(result.sources[0], Source)
        # Sources ordenadas por score descendente
        assert result.sources[0].score >= result.sources[1].score

        # Verifica que embedder foi chamado com o tema
        mock_embedder.embed_query.assert_called_once_with(theme)

        # Verifica que vector_store foi chamado com parametros corretos
        mock_vector_store.search_similar_by_project.assert_called_once_with(
            project_id=project_id,
            query_embedding=[0.1] * 1536,
            top_k=15,
            min_score=0.5,
        )

    def test_compare_filters_by_document_ids(self) -> None:
        """Verifica que chunks de documentos nao solicitados sao filtrados."""
        project_id = str(uuid4())
        doc_a = str(uuid4())
        doc_b = str(uuid4())
        doc_c = str(uuid4())  # documento nao solicitado

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder._use_mock = True

        mock_vector_store = MagicMock()
        mock_vector_store.search_similar_by_project.return_value = [
            _make_chunk("Conteudo doc A", project_id, doc_a),
            _make_chunk("Conteudo doc B", project_id, doc_b),
            _make_chunk("Conteudo doc C (nao solicitado)", project_id, doc_c),
        ]

        service = CompareService(
            embedder=mock_embedder,
            vector_store=mock_vector_store,
        )

        result = service.compare(
            project_id=project_id,
            document_ids=[doc_a, doc_b],
            theme="tema teste",
        )

        # Deve usar apenas chunks de doc_a e doc_b
        assert result.comparison["similarities"] != INSUFFICIENT_CONTEXT
        # Sources nao devem incluir doc_c
        source_docs = {s.document for s in result.sources}
        assert doc_c not in source_docs


class TestCompareServiceInsufficientContext:
    """Testes de fallback quando contexto insuficiente."""

    def test_compare_returns_insufficient_when_no_chunks(self) -> None:
        """Verifica fallback quando vector_store retorna lista vazia."""
        project_id = str(uuid4())
        doc_a = str(uuid4())
        doc_b = str(uuid4())

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder._use_mock = True

        mock_vector_store = MagicMock()
        mock_vector_store.search_similar_by_project.return_value = []

        service = CompareService(
            embedder=mock_embedder,
            vector_store=mock_vector_store,
        )

        result = service.compare(
            project_id=project_id,
            document_ids=[doc_a, doc_b],
            theme="tema teste",
        )

        assert result.comparison["similarities"] == INSUFFICIENT_CONTEXT
        assert result.comparison["differences"] == INSUFFICIENT_CONTEXT
        assert result.comparison["synthesis"] == INSUFFICIENT_CONTEXT
        assert result.sources == []

    def test_compare_returns_insufficient_when_only_one_doc_has_chunks(self) -> None:
        """Verifica fallback quando apenas 1 documento tem chunks."""
        project_id = str(uuid4())
        doc_a = str(uuid4())
        doc_b = str(uuid4())

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder._use_mock = True

        mock_vector_store = MagicMock()
        # Apenas doc_a tem chunks
        mock_vector_store.search_similar_by_project.return_value = [
            _make_chunk("Conteudo doc A", project_id, doc_a),
            _make_chunk("Mais conteudo doc A", project_id, doc_a),
        ]

        service = CompareService(
            embedder=mock_embedder,
            vector_store=mock_vector_store,
        )

        result = service.compare(
            project_id=project_id,
            document_ids=[doc_a, doc_b],
            theme="tema teste",
        )

        assert result.comparison["similarities"] == INSUFFICIENT_CONTEXT
        assert result.sources == []

    def test_compare_returns_insufficient_when_chunks_from_unrequested_docs(
        self,
    ) -> None:
        """Verifica fallback quando chunks existem mas sao de documentos nao solicitados."""
        project_id = str(uuid4())
        doc_a = str(uuid4())
        doc_b = str(uuid4())
        doc_c = str(uuid4())

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder._use_mock = True

        mock_vector_store = MagicMock()
        # Chunks apenas de doc_c (nao solicitado)
        mock_vector_store.search_similar_by_project.return_value = [
            _make_chunk("Conteudo doc C", project_id, doc_c),
        ]

        service = CompareService(
            embedder=mock_embedder,
            vector_store=mock_vector_store,
        )

        result = service.compare(
            project_id=project_id,
            document_ids=[doc_a, doc_b],
            theme="tema teste",
        )

        assert result.comparison["similarities"] == INSUFFICIENT_CONTEXT


class TestCompareServiceParsing:
    """Testes de parsing da resposta do LLM."""

    def test_parse_complete_json_response(self) -> None:
        """Verifica parsing de resposta JSON completa."""
        project_id = str(uuid4())
        doc_a = str(uuid4())
        doc_b = str(uuid4())

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder._use_mock = True

        mock_vector_store = MagicMock()
        mock_vector_store.search_similar_by_project.return_value = [
            _make_chunk("Conteudo doc A", project_id, doc_a),
            _make_chunk("Conteudo doc B", project_id, doc_b),
        ]

        service = CompareService(
            embedder=mock_embedder,
            vector_store=mock_vector_store,
        )

        # Mock do _call_llm para retornar JSON valido completo
        with patch.object(service, "_call_llm") as mock_llm:
            mock_llm.return_value = (
                '{"similarities": "Ambos usam IA", '
                '"differences": "A usa NLP, B usa visao computacional", '
                '"synthesis": "Complementares"}'
            )
            result = service.compare(
                project_id=project_id,
                document_ids=[doc_a, doc_b],
                theme="IA",
            )

        assert result.comparison["similarities"] == "Ambos usam IA"
        assert "NLP" in result.comparison["differences"]
        assert result.comparison["synthesis"] == "Complementares"

    def test_parse_incomplete_json_response(self) -> None:
        """Verifica que chaves ausentes sao preenchidas com 'Nao identificado'."""
        project_id = str(uuid4())
        doc_a = str(uuid4())
        doc_b = str(uuid4())

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder._use_mock = True

        mock_vector_store = MagicMock()
        mock_vector_store.search_similar_by_project.return_value = [
            _make_chunk("Conteudo doc A", project_id, doc_a),
            _make_chunk("Conteudo doc B", project_id, doc_b),
        ]

        service = CompareService(
            embedder=mock_embedder,
            vector_store=mock_vector_store,
        )

        # LLM retorna apenas 2 das 3 chaves
        with patch.object(service, "_call_llm") as mock_llm:
            mock_llm.return_value = (
                '{"similarities": "Ambos usam IA", "synthesis": "OK"}'
            )
            result = service.compare(
                project_id=project_id,
                document_ids=[doc_a, doc_b],
                theme="IA",
            )

        assert result.comparison["similarities"] == "Ambos usam IA"
        assert result.comparison["differences"] == "Nao identificado"
        assert result.comparison["synthesis"] == "OK"

    def test_parse_markdown_code_block_response(self) -> None:
        """Verifica parsing de resposta com code block markdown."""
        project_id = str(uuid4())
        doc_a = str(uuid4())
        doc_b = str(uuid4())

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder._use_mock = True

        mock_vector_store = MagicMock()
        mock_vector_store.search_similar_by_project.return_value = [
            _make_chunk("Conteudo doc A", project_id, doc_a),
            _make_chunk("Conteudo doc B", project_id, doc_b),
        ]

        service = CompareService(
            embedder=mock_embedder,
            vector_store=mock_vector_store,
        )

        # LLM retorna JSON dentro de code block
        with patch.object(service, "_call_llm") as mock_llm:
            mock_llm.return_value = (
                "```json\n"
                '{"similarities": "Ponto A", "differences": "Ponto B", "synthesis": "Ponto C"}\n'
                "```"
            )
            result = service.compare(
                project_id=project_id,
                document_ids=[doc_a, doc_b],
                theme="tema",
            )

        assert result.comparison["similarities"] == "Ponto A"
        assert result.comparison["differences"] == "Ponto B"
        assert result.comparison["synthesis"] == "Ponto C"

    def test_parse_invalid_json_response_uses_heuristics(self) -> None:
        """Verifica fallback heuristico quando LLM retorna texto nao-JSON."""
        project_id = str(uuid4())
        doc_a = str(uuid4())
        doc_b = str(uuid4())

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder._use_mock = True

        mock_vector_store = MagicMock()
        mock_vector_store.search_similar_by_project.return_value = [
            _make_chunk("Conteudo doc A", project_id, doc_a),
            _make_chunk("Conteudo doc B", project_id, doc_b),
        ]

        service = CompareService(
            embedder=mock_embedder,
            vector_store=mock_vector_store,
        )

        # LLM retorna texto com padroes de secao mas nao e JSON
        with patch.object(service, "_call_llm") as mock_llm:
            mock_llm.return_value = (
                "similarities: Ambos tratam de machine learning.\n"
                "differences: Um e supervisionado, outro nao.\n"
                "synthesis: Sao abordagens complementares."
            )
            result = service.compare(
                project_id=project_id,
                document_ids=[doc_a, doc_b],
                theme="ML",
            )

        assert "machine learning" in result.comparison["similarities"]
        assert "supervisionado" in result.comparison["differences"]
        assert "complementares" in result.comparison["synthesis"]

    def test_parse_completely_invalid_response(self) -> None:
        """Verifica fallback quando resposta e totalmente invalida."""
        project_id = str(uuid4())
        doc_a = str(uuid4())
        doc_b = str(uuid4())

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder._use_mock = True

        mock_vector_store = MagicMock()
        mock_vector_store.search_similar_by_project.return_value = [
            _make_chunk("Conteudo doc A", project_id, doc_a),
            _make_chunk("Conteudo doc B", project_id, doc_b),
        ]

        service = CompareService(
            embedder=mock_embedder,
            vector_store=mock_vector_store,
        )

        # LLM retorna texto sem estrutura alguma
        with patch.object(service, "_call_llm") as mock_llm:
            mock_llm.return_value = "Este e um texto sem estrutura nenhuma."
            result = service.compare(
                project_id=project_id,
                document_ids=[doc_a, doc_b],
                theme="tema",
            )

        # Todas as chaves devem ter valor padrao
        assert result.comparison["similarities"] == "Nao identificado"
        assert result.comparison["differences"] == "Nao identificado"
        assert result.comparison["synthesis"] == "Nao identificado"


class TestCompareServiceIsolation:
    """Testes de isolamento por project_id."""

    def test_isolation_by_project_id(self) -> None:
        """Verifica que busca usa project_id correto."""
        project_a = str(uuid4())
        project_b = str(uuid4())
        doc_a = str(uuid4())
        doc_b = str(uuid4())

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder._use_mock = True

        mock_vector_store = MagicMock()
        mock_vector_store.search_similar_by_project.return_value = []

        service = CompareService(
            embedder=mock_embedder,
            vector_store=mock_vector_store,
        )

        service.compare(
            project_id=project_a,
            document_ids=[doc_a, doc_b],
            theme="tema",
        )

        # Verifica que a busca foi feita com project_a
        call_kwargs = mock_vector_store.search_similar_by_project.call_args[1]
        assert call_kwargs["project_id"] == project_a


class TestCompareServiceGrouping:
    """Testes de agrupamento correto por document_id."""

    def test_group_chunks_by_document(self) -> None:
        """Verifica que chunks sao agrupados corretamente por document_id."""
        project_id = str(uuid4())
        doc_a = str(uuid4())
        doc_b = str(uuid4())

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder._use_mock = True

        mock_vector_store = MagicMock()
        mock_vector_store.search_similar_by_project.return_value = [
            _make_chunk("Conteudo A1", project_id, doc_a, page=1),
            _make_chunk("Conteudo A2", project_id, doc_a, page=2),
            _make_chunk("Conteudo B1", project_id, doc_b, page=1),
        ]

        service = CompareService(
            embedder=mock_embedder,
            vector_store=mock_vector_store,
        )

        # Testa metodo de agrupamento diretamente
        chunks = mock_vector_store.search_similar_by_project.return_value
        filtered = [c for c in chunks if c["metadata"]["document_id"] in [doc_a, doc_b]]
        grouped = service._group_chunks_by_document(filtered)

        assert len(grouped) == 2
        assert doc_a in grouped
        assert doc_b in grouped
        assert len(grouped[doc_a]) == 2
        assert len(grouped[doc_b]) == 1
        assert grouped[doc_a][0]["content"] == "Conteudo A1"
        assert grouped[doc_a][1]["content"] == "Conteudo A2"
        assert grouped[doc_b][0]["content"] == "Conteudo B1"

    def test_build_context_separates_documents(self) -> None:
        """Verifica que contexto separa documentos com blocos claros."""
        project_id = str(uuid4())
        doc_a = str(uuid4())
        doc_b = str(uuid4())

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder._use_mock = True

        mock_vector_store = MagicMock()
        mock_vector_store.search_similar_by_project.return_value = [
            _make_chunk("Conteudo A", project_id, doc_a),
            _make_chunk("Conteudo B", project_id, doc_b),
        ]

        service = CompareService(
            embedder=mock_embedder,
            vector_store=mock_vector_store,
        )

        chunks = mock_vector_store.search_similar_by_project.return_value
        filtered = [c for c in chunks if c["metadata"]["document_id"] in [doc_a, doc_b]]
        grouped = service._group_chunks_by_document(filtered)
        context = service._build_context(grouped)

        # Verifica que contexto contem marcadores de documento
        assert f"=== DOCUMENTO: {doc_a} ===" in context
        assert f"=== DOCUMENTO: {doc_b} ===" in context
        assert "Conteudo A" in context
        assert "Conteudo B" in context

    def test_compare_with_three_documents(self) -> None:
        """Verifica comparacao com 3 documentos."""
        project_id = str(uuid4())
        doc_a = str(uuid4())
        doc_b = str(uuid4())
        doc_c = str(uuid4())

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder._use_mock = True

        mock_vector_store = MagicMock()
        mock_vector_store.search_similar_by_project.return_value = [
            _make_chunk("Conteudo A", project_id, doc_a),
            _make_chunk("Conteudo B", project_id, doc_b),
            _make_chunk("Conteudo C", project_id, doc_c),
        ]

        service = CompareService(
            embedder=mock_embedder,
            vector_store=mock_vector_store,
        )

        result = service.compare(
            project_id=project_id,
            document_ids=[doc_a, doc_b, doc_c],
            theme="tema",
        )

        assert result.comparison["similarities"] != INSUFFICIENT_CONTEXT
        assert len(result.sources) == 3
