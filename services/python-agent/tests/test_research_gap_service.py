"""
Testes unitarios do ResearchGapService.

Cobertura:
- Lacunas com corpus suficiente (mocks de embedder, vector_store, LLM).
- Corpus vazio (lista vazia de gaps).
- Parsing quando LLM retorna formato incompleto.
- Calculo de confidence baseado em quantidade de chunks.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.domain.research_gap_service import (
    ResearchGapError,
    ResearchGapService,
)
from app.schemas.contracts_v1 import ResearchGapResponse


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


class TestResearchGapServiceWithCorpus:
    """Testes de identificacao de lacunas com corpus suficiente."""

    def test_find_gaps_returns_list_with_corpus(self) -> None:
        """Verifica que lacunas sao retornadas quando ha corpus."""
        project_id = str(uuid4())

        # Mocks
        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder._use_mock = True

        mock_vector_store = MagicMock()
        mock_vector_store.search_similar_by_project.return_value = [
            _make_chunk(
                content="Este estudo investiga o impacto de IA na educacao superior.",
                project_id=project_id,
                document_id=str(uuid4()),
            ),
            _make_chunk(
                content="A metodologia utilizou survey com 500 estudantes.",
                project_id=project_id,
                document_id=str(uuid4()),
            ),
            _make_chunk(
                content="Os resultados indicam tendencia positiva.",
                project_id=project_id,
                document_id=str(uuid4()),
            ),
        ]

        service = ResearchGapService(
            embedder=mock_embedder,
            vector_store=mock_vector_store,
        )

        result = service.find_gaps(project_id=project_id)

        # Verifica estrutura
        assert isinstance(result, ResearchGapResponse)
        assert str(result.project_id) == project_id
        assert len(result.gaps) > 0

        # Verifica que embedder foi chamado
        mock_embedder.embed_query.assert_called_once()

        # Verifica que vector_store foi chamado com parametros corretos
        mock_vector_store.search_similar_by_project.assert_called_once()

    def test_find_gaps_with_theme_uses_theme_embedding(self) -> None:
        """Verifica que quando theme e informado, usa embedding do tema."""
        project_id = str(uuid4())
        theme = "inteligencia artificial na educacao"

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder._use_mock = True

        mock_vector_store = MagicMock()
        mock_vector_store.search_similar_by_project.return_value = [
            _make_chunk("Conteudo sobre IA", project_id, str(uuid4())),
        ]

        service = ResearchGapService(
            embedder=mock_embedder,
            vector_store=mock_vector_store,
        )

        service.find_gaps(project_id=project_id, theme=theme)

        # Verifica que embedder foi chamado com o tema
        mock_embedder.embed_query.assert_called_once_with(theme)


class TestResearchGapServiceEmptyCorpus:
    """Testes de fallback quando corpus vazio."""

    def test_find_gaps_returns_empty_when_no_chunks(self) -> None:
        """Verifica que retorna lista vazia quando vector_store retorna vazio."""
        project_id = str(uuid4())

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder._use_mock = True

        mock_vector_store = MagicMock()
        mock_vector_store.search_similar_by_project.return_value = []

        service = ResearchGapService(
            embedder=mock_embedder,
            vector_store=mock_vector_store,
        )

        result = service.find_gaps(project_id=project_id)

        assert isinstance(result, ResearchGapResponse)
        assert result.gaps == []
        assert str(result.project_id) == project_id


class TestResearchGapServiceParsing:
    """Testes de parsing da resposta do LLM."""

    def test_parse_complete_json_response(self) -> None:
        """Verifica parsing de resposta JSON completa com lacunas validas."""
        project_id = str(uuid4())

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder._use_mock = True

        mock_vector_store = MagicMock()
        mock_vector_store.search_similar_by_project.return_value = [
            _make_chunk("Conteudo teste", project_id, str(uuid4())),
        ]

        service = ResearchGapService(
            embedder=mock_embedder,
            vector_store=mock_vector_store,
        )

        # Mock do _call_llm para retornar JSON valido
        with patch.object(service, "_call_llm") as mock_llm:
            mock_llm.return_value = (
                '[{"gap_title": "Lacuna A", "why_gap": "Explicacao A", '
                '"suggested_questions": ["Pergunta 1?", "Pergunta 2?"], '
                '"evidence_sources": [{"document": "doc1", "page": 1, "score": 0.9}]}]'
            )
            result = service.find_gaps(project_id=project_id)

        assert len(result.gaps) == 1
        assert result.gaps[0].gap_title == "Lacuna A"
        assert result.gaps[0].why_gap == "Explicacao A"
        assert len(result.gaps[0].suggested_questions) == 2
        assert len(result.gaps[0].evidence_sources) == 1

    def test_parse_incomplete_json_response(self) -> None:
        """Verifica que itens incompletos sao ignorados."""
        project_id = str(uuid4())

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder._use_mock = True

        mock_vector_store = MagicMock()
        mock_vector_store.search_similar_by_project.return_value = [
            _make_chunk("Conteudo teste", project_id, str(uuid4())),
        ]

        service = ResearchGapService(
            embedder=mock_embedder,
            vector_store=mock_vector_store,
        )

        # LLM retorna lista com item incompleto (sem why_gap)
        with patch.object(service, "_call_llm") as mock_llm:
            mock_llm.return_value = (
                '[{"gap_title": "Lacuna A", "why_gap": "", '
                '"suggested_questions": [], "evidence_sources": []}]'
            )
            result = service.find_gaps(project_id=project_id)

        # Item incompleto deve ser ignorado
        assert len(result.gaps) == 0

    def test_parse_invalid_json_response(self) -> None:
        """Verifica fallback quando LLM retorna texto invalido."""
        project_id = str(uuid4())

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder._use_mock = True

        mock_vector_store = MagicMock()
        mock_vector_store.search_similar_by_project.return_value = [
            _make_chunk("Conteudo teste", project_id, str(uuid4())),
        ]

        service = ResearchGapService(
            embedder=mock_embedder,
            vector_store=mock_vector_store,
        )

        # LLM retorna texto nao-JSON
        with patch.object(service, "_call_llm") as mock_llm:
            mock_llm.return_value = "Este e um texto sem estrutura JSON."
            result = service.find_gaps(project_id=project_id)

        # Deve retornar lista vazia
        assert result.gaps == []

    def test_parse_markdown_code_block_response(self) -> None:
        """Verifica parsing de resposta com code block markdown."""
        project_id = str(uuid4())

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder._use_mock = True

        mock_vector_store = MagicMock()
        mock_vector_store.search_similar_by_project.return_value = [
            _make_chunk("Conteudo teste", project_id, str(uuid4())),
        ]

        service = ResearchGapService(
            embedder=mock_embedder,
            vector_store=mock_vector_store,
        )

        # LLM retorna JSON dentro de code block
        with patch.object(service, "_call_llm") as mock_llm:
            mock_llm.return_value = (
                "```json\n"
                '[{"gap_title": "Lacuna B", "why_gap": "Explicacao B", '
                '"suggested_questions": ["Pergunta?"], '
                '"evidence_sources": []}]\n'
                "```"
            )
            result = service.find_gaps(project_id=project_id)

        assert len(result.gaps) == 1
        assert result.gaps[0].gap_title == "Lacuna B"


class TestResearchGapServiceConfidence:
    """Testes de calculo de confidence."""

    def test_confidence_high_when_more_than_10_chunks(self) -> None:
        """Verifica confidence high quando > 10 chunks."""
        project_id = str(uuid4())

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder._use_mock = True

        mock_vector_store = MagicMock()
        # 12 chunks
        mock_vector_store.search_similar_by_project.return_value = [
            _make_chunk(f"Conteudo {i}", project_id, str(uuid4())) for i in range(12)
        ]

        service = ResearchGapService(
            embedder=mock_embedder,
            vector_store=mock_vector_store,
        )

        with patch.object(service, "_call_llm") as mock_llm:
            mock_llm.return_value = (
                '[{"gap_title": "Lacuna X", "why_gap": "Explicacao X", '
                '"suggested_questions": [], "evidence_sources": []}]'
            )
            result = service.find_gaps(project_id=project_id)

        assert result.gaps[0].confidence == "high"

    def test_confidence_medium_when_5_to_10_chunks(self) -> None:
        """Verifica confidence medium quando 5-10 chunks."""
        project_id = str(uuid4())

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder._use_mock = True

        mock_vector_store = MagicMock()
        # 7 chunks
        mock_vector_store.search_similar_by_project.return_value = [
            _make_chunk(f"Conteudo {i}", project_id, str(uuid4())) for i in range(7)
        ]

        service = ResearchGapService(
            embedder=mock_embedder,
            vector_store=mock_vector_store,
        )

        with patch.object(service, "_call_llm") as mock_llm:
            mock_llm.return_value = (
                '[{"gap_title": "Lacuna Y", "why_gap": "Explicacao Y", '
                '"suggested_questions": [], "evidence_sources": []}]'
            )
            result = service.find_gaps(project_id=project_id)

        assert result.gaps[0].confidence == "medium"

    def test_confidence_low_when_less_than_5_chunks(self) -> None:
        """Verifica confidence low quando < 5 chunks."""
        project_id = str(uuid4())

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder._use_mock = True

        mock_vector_store = MagicMock()
        # 3 chunks
        mock_vector_store.search_similar_by_project.return_value = [
            _make_chunk(f"Conteudo {i}", project_id, str(uuid4())) for i in range(3)
        ]

        service = ResearchGapService(
            embedder=mock_embedder,
            vector_store=mock_vector_store,
        )

        with patch.object(service, "_call_llm") as mock_llm:
            mock_llm.return_value = (
                '[{"gap_title": "Lacuna Z", "why_gap": "Explicacao Z", '
                '"suggested_questions": [], "evidence_sources": []}]'
            )
            result = service.find_gaps(project_id=project_id)

        assert result.gaps[0].confidence == "low"

    def test_calculate_confidence_direct(self) -> None:
        """Verifica metodo _calculate_confidence diretamente."""
        service = ResearchGapService()

        assert service._calculate_confidence(0) == "low"
        assert service._calculate_confidence(3) == "low"
        assert service._calculate_confidence(4) == "low"
        assert service._calculate_confidence(5) == "medium"
        assert service._calculate_confidence(10) == "medium"
        assert service._calculate_confidence(11) == "high"
        assert service._calculate_confidence(50) == "high"
