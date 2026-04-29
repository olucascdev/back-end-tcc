"""
Testes do pipeline de avaliacao RAG academica.

Cobertura:
- Calculo de faithfulness com entrada conhecida
- Calculo de answer relevancy via cosine similarity
- Calculo de context precision com heuristica hibrida
- Calculo de context recall com IDs esperados vs recuperados
- Execucao end-to-end do script com dataset mock minimo
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Adiciona raiz do projeto ao path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.evaluation import (
    compute_answer_relevancy,
    compute_context_precision,
    compute_context_recall,
    compute_faithfulness,
)


# ---------------------------------------------------------------------------
# Testes de Faithfulness
# ---------------------------------------------------------------------------


class TestComputeFaithfulness:
    """Testes da metrica de faithfulness."""

    def test_faithfulness_full_support(self) -> None:
        """Todas as sentencas da resposta sao suportadas pelo contexto."""
        answer = (
            "A metodologia e qualitativa. Os dados foram coletados por entrevistas."
        )
        context_chunks = [
            {
                "content": (
                    "A metodologia utilizada nesta pesquisa e qualitativa de natureza "
                    "exploratoria. Os dados foram coletados por meio de entrevistas "
                    "semiestruturadas com participantes."
                )
            }
        ]

        result = compute_faithfulness(answer, context_chunks)

        # Ambas as sentencas devem ser suportadas
        assert result == 1.0

    def test_faithfulness_partial_support(self) -> None:
        """Apenas algumas sentencas sao suportadas pelo contexto."""
        answer = "A metodologia e qualitativa. O resultado foi 99 por cento de acerto."
        context_chunks = [
            {
                "content": (
                    "A metodologia utilizada nesta pesquisa e qualitativa de natureza "
                    "exploratoria."
                )
            }
        ]

        result = compute_faithfulness(answer, context_chunks)

        # Apenas 1 de 2 sentencas suportada
        assert result == pytest.approx(0.5, abs=0.01)

    def test_faithfulness_no_support(self) -> None:
        """Nenhuma sentenca e suportada pelo contexto."""
        answer = "O resultado foi 99 por cento de acerto no teste de fisica quantica."
        context_chunks = [
            {"content": "A metodologia e qualitativa com entrevistas semiestruturadas."}
        ]

        result = compute_faithfulness(answer, context_chunks)

        assert result == 0.0

    def test_faithfulness_empty_answer(self) -> None:
        """Resposta vazia retorna 0.0."""
        context_chunks = [{"content": "Contexto qualquer"}]

        result = compute_faithfulness("", context_chunks)

        assert result == 0.0

    def test_faithfulness_empty_context(self) -> None:
        """Contexto vazio retorna 0.0."""
        result = compute_faithfulness("Resposta qualquer", [])

        assert result == 0.0

    def test_faithfulness_multiple_chunks(self) -> None:
        """Sentencas podem ser suportadas por chunks diferentes."""
        answer = "A metodologia e qualitativa. A amostra tem 15 participantes."
        context_chunks = [
            {
                "content": "A metodologia utilizada e qualitativa de natureza exploratoria."
            },
            {"content": "A amostra foi composta por 15 participantes selecionados."},
        ]

        result = compute_faithfulness(answer, context_chunks)

        assert result == 1.0


# ---------------------------------------------------------------------------
# Testes de Answer Relevancy
# ---------------------------------------------------------------------------


class TestComputeAnswerRelevancy:
    """Testes da metrica de answer relevancy."""

    def test_answer_relevancy_identical_vectors(self) -> None:
        """Vetores identicos tem similaridade 1.0."""
        vec = [0.1, 0.2, 0.3, 0.4, 0.5]

        result = compute_answer_relevancy(vec, vec)

        assert result == pytest.approx(1.0, abs=1e-6)

    def test_answer_relevancy_orthogonal_vectors(self) -> None:
        """Vetores ortogonais tem similaridade proxima de 0."""
        v1 = [1.0, 0.0, 0.0]
        v2 = [0.0, 1.0, 0.0]

        result = compute_answer_relevancy(v1, v2)

        assert result == pytest.approx(0.0, abs=1e-6)

    def test_answer_relevancy_opposite_vectors(self) -> None:
        """Vetores opostos tem similaridade -1.0."""
        v1 = [1.0, 0.0, 0.0]
        v2 = [-1.0, 0.0, 0.0]

        result = compute_answer_relevancy(v1, v2)

        assert result == pytest.approx(-1.0, abs=1e-6)

    def test_answer_relevancy_zero_vector(self) -> None:
        """Vetor nulo retorna 0.0."""
        v1 = [0.0, 0.0, 0.0]
        v2 = [1.0, 2.0, 3.0]

        result = compute_answer_relevancy(v1, v2)

        assert result == 0.0

    def test_answer_relevancy_realistic_embeddings(self) -> None:
        """Embeddings realisticos (normalizados) tem alta similaridade para textos relacionados."""
        # Simula embeddings normalizados de textos semanticamente proximos
        v1 = [0.02] * 10 + [0.1] * 5  # embedding da pergunta
        v2 = [0.02] * 10 + [0.09] * 5  # embedding da resposta relacionada

        result = compute_answer_relevancy(v1, v2)

        # Deve ser alta (proxima de 1)
        assert result > 0.9


# ---------------------------------------------------------------------------
# Testes de Context Precision
# ---------------------------------------------------------------------------


class TestComputeContextPrecision:
    """Testes da metrica de context precision."""

    def test_context_precision_all_relevant(self) -> None:
        """Todos os chunks recuperados sao relevantes."""
        question = "Qual e a metodologia da pesquisa?"
        retrieved_chunks = [
            {"content": "A metodologia utilizada e qualitativa com entrevistas."},
            {"content": "A metodologia da pesquisa segue abordagem exploratoria."},
        ]

        result = compute_context_precision(question, retrieved_chunks)

        assert result == 1.0

    def test_context_precision_partial_relevant(self) -> None:
        """Apenas alguns chunks sao relevantes."""
        question = "Qual e a metodologia da pesquisa?"
        retrieved_chunks = [
            {"content": "A metodologia utilizada e qualitativa com entrevistas."},
            {"content": "O clima hoje esta ensolarado com temperatura de 30 graus."},
        ]

        result = compute_context_precision(question, retrieved_chunks)

        # 1 de 2 chunks relevante
        assert result == pytest.approx(0.5, abs=0.01)

    def test_context_precision_none_relevant(self) -> None:
        """Nenhum chunk e relevante para a pergunta."""
        question = "Qual e a metodologia da pesquisa?"
        retrieved_chunks = [
            {"content": "A receita de bolo leva farinha e acucar."},
            {"content": "O carro tem motor a combustao e transmissao automatica."},
        ]

        result = compute_context_precision(question, retrieved_chunks)

        assert result == 0.0

    def test_context_precision_empty_chunks(self) -> None:
        """Lista vazia de chunks retorna 0.0."""
        result = compute_context_precision("pergunta qualquer", [])

        assert result == 0.0

    def test_context_precision_with_embeddings(self) -> None:
        """Criterio de embedding complementa keyword overlap."""
        question = "Qual e a metodologia?"
        retrieved_chunks = [
            {"content": "A abordagem metodologica e qualitativa."},
        ]
        # Embeddings identicos → alta similaridade
        question_emb = [0.1] * 10
        chunk_emb = [[0.1] * 10]

        result = compute_context_precision(
            question,
            retrieved_chunks,
            question_embedding=question_emb,
            chunk_embeddings=chunk_emb,
        )

        # Deve ser relevante por embedding (e possivelmente por keyword)
        assert result == 1.0


# ---------------------------------------------------------------------------
# Testes de Context Recall
# ---------------------------------------------------------------------------


class TestComputeContextRecall:
    """Testes da metrica de context recall."""

    def test_context_recall_full(self) -> None:
        """Todos os chunks esperados foram recuperados."""
        expected = {"doc1-chunk1", "doc1-chunk2", "doc1-chunk3"}
        retrieved = {"doc1-chunk1", "doc1-chunk2", "doc1-chunk3"}

        result = compute_context_recall(expected, retrieved)

        assert result == 1.0

    def test_context_recall_partial(self) -> None:
        """Apenas alguns chunks esperados foram recuperados."""
        expected = {"doc1-chunk1", "doc1-chunk2", "doc1-chunk3"}
        retrieved = {"doc1-chunk1", "doc1-chunk2"}

        result = compute_context_recall(expected, retrieved)

        assert result == pytest.approx(2 / 3, abs=0.01)

    def test_context_recall_none(self) -> None:
        """Nenhum chunk esperado foi recuperado."""
        expected = {"doc1-chunk1", "doc1-chunk2"}
        retrieved = {"doc2-chunk1", "doc2-chunk2"}

        result = compute_context_recall(expected, retrieved)

        assert result == 0.0

    def test_context_recall_empty_expected(self) -> None:
        """Sem chunks esperados retorna 1.0."""
        result = compute_context_recall(set(), {"doc1-chunk1"})

        assert result == 1.0

    def test_context_recall_extra_retrieved(self) -> None:
        """Chunks extras recuperados nao afetam recall."""
        expected = {"doc1-chunk1"}
        retrieved = {"doc1-chunk1", "doc2-chunk1", "doc3-chunk1"}

        result = compute_context_recall(expected, retrieved)

        assert result == 1.0


# ---------------------------------------------------------------------------
# Testes End-to-End do Script
# ---------------------------------------------------------------------------


class TestEvaluateRagScript:
    """Testes end-to-end do script de avaliacao."""

    @pytest.fixture
    def mock_dataset(self, tmp_path: Path) -> Path:
        """Cria golden dataset mock minimo para testes."""
        dataset = {
            "version": "1.0",
            "seed": 42,
            "model": "text-embedding-3-small",
            "questions": [
                {
                    "id": "test-q1",
                    "project_id": "test-project",
                    "question": "Qual e a metodologia?",
                    "expected_context_ids": ["ctx-1", "ctx-2"],
                    "reference_answer": "A metodologia e qualitativa com entrevistas.",
                },
                {
                    "id": "test-q2",
                    "project_id": "test-project",
                    "question": "Quais sao os resultados?",
                    "expected_context_ids": ["ctx-3"],
                    "reference_answer": "Os resultados mostram aumento de 35 por cento.",
                },
            ],
        }

        dataset_path = tmp_path / "mock_golden_dataset.json"
        with open(dataset_path, "w", encoding="utf-8") as f:
            json.dump(dataset, f)

        return dataset_path

    def test_load_golden_dataset(self, mock_dataset: Path) -> None:
        """Carregamento do golden dataset funciona corretamente."""
        from scripts.evaluate_rag import load_golden_dataset

        data = load_golden_dataset(str(mock_dataset))

        assert data["version"] == "1.0"
        assert len(data["questions"]) == 2
        assert data["questions"][0]["id"] == "test-q1"

    def test_load_golden_dataset_not_found(self) -> None:
        """Arquivo inexistente levanta FileNotFoundError."""
        from scripts.evaluate_rag import load_golden_dataset

        with pytest.raises(FileNotFoundError):
            load_golden_dataset("/caminho/inexistente/dataset.json")

    def test_load_golden_dataset_invalid(self, tmp_path: Path) -> None:
        """Dataset sem chaves obrigatorias levanta ValueError."""
        invalid_path = tmp_path / "invalid.json"
        with open(invalid_path, "w") as f:
            json.dump({"foo": "bar"}, f)

        from scripts.evaluate_rag import load_golden_dataset

        with pytest.raises(ValueError):
            load_golden_dataset(str(invalid_path))

    @patch("scripts.evaluate_rag.OpenAIEmbedder")
    def test_evaluate_question(
        self, mock_embedder_cls: MagicMock, mock_dataset: Path
    ) -> None:
        """Avaliacao de uma unica pergunta retorna metricas validas."""
        from scripts.evaluate_rag import evaluate_question

        # Configura mock do embedder
        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder_cls.return_value = mock_embedder

        dataset = json.loads(mock_dataset.read_text())
        question = dataset["questions"][0]

        result = evaluate_question(question, mock_embedder, "project_only")

        assert result["question_id"] == "test-q1"
        assert result["mode"] == "project_only"
        assert "faithfulness" in result["metrics"]
        assert "answer_relevancy" in result["metrics"]
        assert "context_precision" in result["metrics"]
        assert "context_recall" in result["metrics"]

        # Todas as metricas devem estar entre 0 e 1
        for metric_name, value in result["metrics"].items():
            assert 0.0 <= value <= 1.0, f"{metric_name} fora do intervalo [0, 1]"

    @patch("scripts.evaluate_rag.OpenAIEmbedder")
    def test_run_evaluation(
        self, mock_embedder_cls: MagicMock, mock_dataset: Path
    ) -> None:
        """Execucao completa retorna resultados para todas as perguntas e modos."""
        from scripts.evaluate_rag import run_evaluation

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder_cls.return_value = mock_embedder

        dataset = json.loads(mock_dataset.read_text())

        results = run_evaluation(dataset, mock_embedder, ["project_only"])

        # 2 perguntas x 1 modo = 2 resultados
        assert len(results) == 2
        assert all(r["mode"] == "project_only" for r in results)

    @patch("scripts.evaluate_rag.OpenAIEmbedder")
    def test_compute_summary(
        self, mock_embedder_cls: MagicMock, mock_dataset: Path
    ) -> None:
        """Sumario calcula medias corretamente."""
        from scripts.evaluate_rag import compute_summary, run_evaluation

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder_cls.return_value = mock_embedder

        dataset = json.loads(mock_dataset.read_text())
        results = run_evaluation(dataset, mock_embedder, ["project_only"])
        summary = compute_summary(results)

        assert summary["total_questions"] == 2
        assert summary["total_evaluations"] == 2
        assert "global_averages" in summary
        assert "mode_averages" in summary
        assert "project_only" in summary["mode_averages"]

    @patch("scripts.evaluate_rag.OpenAIEmbedder")
    def test_export_outputs(
        self, mock_embedder_cls: MagicMock, mock_dataset: Path, tmp_path: Path
    ) -> None:
        """Exportacao gera arquivos JSON, CSV e sumario."""
        from scripts.evaluate_rag import (
            compute_summary,
            export_csv,
            export_json,
            export_summary,
            run_evaluation,
        )

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder_cls.return_value = mock_embedder

        dataset = json.loads(mock_dataset.read_text())
        results = run_evaluation(dataset, mock_embedder, ["project_only"])
        summary = compute_summary(results)

        output_dir = tmp_path / "reports"
        output_dir.mkdir()

        json_path = export_json(results, summary, output_dir)
        csv_path = export_csv(results, output_dir)
        summary_path = export_summary(summary, output_dir)

        assert json_path.exists()
        assert csv_path.exists()
        assert summary_path.exists()

        # Verifica conteudo do JSON
        with open(json_path, "r") as f:
            data = json.load(f)
        assert "summary" in data
        assert "results" in data
        assert len(data["results"]) == 2

    @patch("scripts.evaluate_rag.OpenAIEmbedder")
    def test_main_cli_both_modes(
        self, mock_embedder_cls: MagicMock, mock_dataset: Path, tmp_path: Path
    ) -> None:
        """Execucao via main() com modo 'both' gera resultados para ambos os modos."""
        from scripts.evaluate_rag import main

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = [0.1] * 1536
        mock_embedder_cls.return_value = mock_embedder

        output_dir = tmp_path / "cli_output"

        main(
            argv=[
                "--dataset",
                str(mock_dataset),
                "--output",
                str(output_dir),
                "--mode",
                "both",
            ]
        )

        # Verifica que arquivos foram gerados
        assert (output_dir / "evaluation_results.json").exists()
        assert (output_dir / "evaluation_results.csv").exists()
        assert (output_dir / "executive_summary.txt").exists()

        # Verifica que ambos os modos foram avaliados
        with open(output_dir / "evaluation_results.json", "r") as f:
            data = json.load(f)

        modes_in_results = set(r["mode"] for r in data["results"])
        assert "project_only" in modes_in_results
        assert "project_plus_public" in modes_in_results
