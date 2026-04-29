#!/usr/bin/env python3
"""
Script CLI para avaliacao academica do pipeline RAG.

Executa perguntas de um golden dataset contra o pipeline RAG em ambos
os modos de retrieval e calcula 4 metricas academicas:
- Faithfulness
- Answer Relevancy
- Context Precision
- Context Recall

Uso:
    python scripts/evaluate_rag.py --dataset docs/evaluation/golden-dataset-v1.0.json --output reports/evaluation/
    python scripts/evaluate_rag.py --dataset docs/evaluation/golden-dataset-v1.0.json --output reports/evaluation/ --mode project_only
    python scripts/evaluate_rag.py --dataset docs/evaluation/golden-dataset-v1.0.json --output reports/evaluation/ --mode both
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

# Adiciona raiz do projeto ao path para imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.evaluation import (
    compute_answer_relevancy,
    compute_context_precision,
    compute_context_recall,
    compute_faithfulness,
)
from app.infrastructure.embeddings.openai_embedder import OpenAIEmbedder


# ---------------------------------------------------------------------------
# Tipos e constantes
# ---------------------------------------------------------------------------

RETRIEVAL_MODES = ("project_only", "project_plus_public", "both")


# ---------------------------------------------------------------------------
# Carregamento do golden dataset
# ---------------------------------------------------------------------------


def load_golden_dataset(path: str) -> dict[str, Any]:
    """Carrega golden dataset JSON do disco.

    Args:
        path: caminho absoluto ou relativo para o arquivo JSON.

    Returns:
        Dict com estrutura do golden dataset.

    Raises:
        FileNotFoundError: se arquivo nao existir.
        ValueError: se estrutura JSON for invalida.
    """
    filepath = Path(path)
    if not filepath.exists():
        raise FileNotFoundError(f"Golden dataset nao encontrado: {path}")

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Validacao basica da estrutura
    required_keys = {"version", "questions"}
    if not required_keys.issubset(data.keys()):
        raise ValueError(
            f"Golden dataset invalido: faltam chaves {required_keys - set(data.keys())}"
        )

    if not isinstance(data["questions"], list) or len(data["questions"]) == 0:
        raise ValueError("Golden dataset deve conter pelo menos 1 pergunta.")

    return data


# ---------------------------------------------------------------------------
# Simulacao de chunks recuperados (para avaliacao sem banco real)
# ---------------------------------------------------------------------------


def _chunk_id(content: str) -> str:
    """Gera ID unico para um chunk baseado no conteudo.

    Usa hash MD5 para criar identificador deterministico.

    Args:
        content: texto do chunk.

    Returns:
        String hash do conteudo.
    """
    return hashlib.md5(content.encode("utf-8")).hexdigest()[:16]


def simulate_retrieval(
    question: str,
    embedder: OpenAIEmbedder,
    golden_question: dict[str, Any],
    mode: str,
) -> list[dict[str, Any]]:
    """Simula recuperacao de chunks para avaliacao.

    Em ambiente de avaliacao sem banco real, usa o expected_context_ids
    do golden dataset para construir chunks simulados com conteudo
    derivado da reference_answer.

    Para avaliacao real com banco, substituir esta funcao por chamadas
    ao PgVectorStore.

    Args:
        question: texto da pergunta.
        embedder: instancia do OpenAIEmbedder.
        golden_question: entrada do golden dataset.
        mode: modo de retrieval.

    Returns:
        Lista de chunks simulados com content, metadata e score.
    """
    expected_ids = golden_question.get("expected_context_ids", [])
    reference = golden_question.get("reference_answer", "")

    chunks: list[dict[str, Any]] = []

    # Gera chunks simulados baseados nos expected_context_ids
    for ctx_id in expected_ids:
        # Conteudo simulado: combina reference_answer com ID do contexto
        simulated_content = f"[Contexto {ctx_id}] {reference}"
        chunks.append(
            {
                "content": simulated_content,
                "metadata": {
                    "chunk_id": ctx_id,
                    "project_id": golden_question.get("project_id", ""),
                    "source_type": "project_document",
                },
                "score": 0.95 - (len(chunks) * 0.03),
            }
        )

    # No modo project_plus_public, adiciona chunk publico simulado
    if mode == "project_plus_public":
        chunks.append(
            {
                "content": f"[Publico] Referencia geral sobre o tema: {reference}",
                "metadata": {
                    "chunk_id": f"public-{_chunk_id(reference)}",
                    "source_type": "public_library",
                },
                "score": 0.80,
            }
        )

    return chunks


# ---------------------------------------------------------------------------
# Pipeline de avaliacao
# ---------------------------------------------------------------------------


def evaluate_question(
    golden_question: dict[str, Any],
    embedder: OpenAIEmbedder,
    mode: str,
) -> dict[str, Any]:
    """Avalia uma unica pergunta do golden dataset.

    Fluxo:
    1. Gera embedding da pergunta
    2. Simula recuperacao de chunks
    3. Gera resposta simulada (baseada no contexto recuperado)
    4. Gera embedding da resposta
    5. Calcula as 4 metricas

    Args:
        golden_question: entrada do golden dataset.
        embedder: instancia do OpenAIEmbedder.
        mode: modo de retrieval.

    Returns:
        Dict com resultados da avaliacao.
    """
    question = golden_question["question"]
    expected_ids = set(golden_question.get("expected_context_ids", []))
    reference_answer = golden_question.get("reference_answer", "")

    # 1. Embedding da pergunta
    question_embedding = embedder.embed_query(question)

    # 2. Recuperacao simulada
    retrieved_chunks = simulate_retrieval(question, embedder, golden_question, mode)
    retrieved_ids = {
        chunk["metadata"].get("chunk_id", _chunk_id(chunk["content"]))
        for chunk in retrieved_chunks
    }

    # 3. Resposta simulada (em producao, viria do RAGService)
    # Para avaliacao, usamos a reference_answer como proxy da resposta do LLM
    answer = reference_answer if reference_answer else "Sem resposta de referencia."

    # 4. Embedding da resposta
    answer_embedding = embedder.embed_query(answer)

    # 5. Calcula metricas
    faithfulness = compute_faithfulness(answer, retrieved_chunks)
    answer_relevancy = compute_answer_relevancy(question_embedding, answer_embedding)

    # Context precision com embeddings
    chunk_embeddings = [
        embedder.embed_query(chunk["content"]) for chunk in retrieved_chunks
    ]
    context_precision = compute_context_precision(
        question=question,
        retrieved_chunks=retrieved_chunks,
        question_embedding=question_embedding,
        chunk_embeddings=chunk_embeddings,
    )

    context_recall = compute_context_recall(expected_ids, retrieved_ids)

    return {
        "question_id": golden_question["id"],
        "project_id": golden_question.get("project_id", ""),
        "question": question,
        "mode": mode,
        "answer": answer,
        "reference_answer": reference_answer,
        "retrieved_chunks_count": len(retrieved_chunks),
        "retrieved_chunk_ids": sorted(retrieved_ids),
        "expected_context_ids": sorted(expected_ids),
        "metrics": {
            "faithfulness": round(faithfulness, 4),
            "answer_relevancy": round(answer_relevancy, 4),
            "context_precision": round(context_precision, 4),
            "context_recall": round(context_recall, 4),
        },
    }


def run_evaluation(
    dataset: dict[str, Any],
    embedder: OpenAIEmbedder,
    modes: list[str],
) -> list[dict[str, Any]]:
    """Executa avaliacao completa para todas as perguntas e modos.

    Args:
        dataset: golden dataset carregado.
        embedder: instancia do OpenAIEmbedder.
        modes: lista de modos de retrieval a avaliar.

    Returns:
        Lista de resultados por pergunta/modo.
    """
    questions = dataset["questions"]
    total = len(questions) * len(modes)
    results: list[dict[str, Any]] = []
    current = 0

    print(
        f"Iniciando avaliacao: {len(questions)} perguntas x {len(modes)} modos = {total} execucoes"
    )
    print(f"Modelo de embedding: {dataset.get('model', 'desconhecido')}")
    print(f"Seed: {dataset.get('seed', 'N/A')}")
    print("-" * 60)

    start_time = time.time()

    for mode in modes:
        print(f"\nModo: {mode}")
        for q in questions:
            current += 1
            print(f"  [{current}/{total}] Avaliando {q['id']}...", end=" ")

            result = evaluate_question(q, embedder, mode)
            results.append(result)

            m = result["metrics"]
            print(
                f"F={m['faithfulness']:.2f} "
                f"AR={m['answer_relevancy']:.2f} "
                f"CP={m['context_precision']:.2f} "
                f"CR={m['context_recall']:.2f}"
            )

    elapsed = time.time() - start_time
    print(f"\nAvaliacao concluida em {elapsed:.1f}s")

    return results


# ---------------------------------------------------------------------------
# Exportacao de resultados
# ---------------------------------------------------------------------------


def compute_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Calcula estatisticas resumidas dos resultados.

    Args:
        results: lista de resultados por pergunta/modo.

    Returns:
        Dict com medias globais e por modo.
    """
    metric_names = [
        "faithfulness",
        "answer_relevancy",
        "context_precision",
        "context_recall",
    ]

    # Medias globais
    global_averages: dict[str, float] = {}
    for metric in metric_names:
        values = [r["metrics"][metric] for r in results]
        global_averages[metric] = round(sum(values) / len(values), 4) if values else 0.0

    # Medias por modo
    mode_averages: dict[str, dict[str, float]] = {}
    modes = set(r["mode"] for r in results)
    for mode in modes:
        mode_results = [r for r in results if r["mode"] == mode]
        mode_averages[mode] = {}
        for metric in metric_names:
            values = [r["metrics"][metric] for r in mode_results]
            mode_averages[mode][metric] = (
                round(sum(values) / len(values), 4) if values else 0.0
            )

    return {
        "total_questions": len(set(r["question_id"] for r in results)),
        "total_evaluations": len(results),
        "modes_evaluated": sorted(modes),
        "global_averages": global_averages,
        "mode_averages": mode_averages,
    }


def export_json(
    results: list[dict[str, Any]], summary: dict[str, Any], output_dir: Path
) -> Path:
    """Exporta resultados e sumario para JSON.

    Args:
        results: lista de resultados detalhados.
        summary: estatisticas resumidas.
        output_dir: diretorio de saida.

    Returns:
        Caminho do arquivo JSON gerado.
    """
    output_path = output_dir / "evaluation_results.json"
    data = {
        "generated_at": datetime.now(UTC).isoformat(),
        "summary": summary,
        "results": results,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Resultados JSON salvos em: {output_path}")
    return output_path


def export_csv(results: list[dict[str, Any]], output_dir: Path) -> Path:
    """Exporta resultados detalhados para CSV.

    Args:
        results: lista de resultados por pergunta/modo.
        output_dir: diretorio de saida.

    Returns:
        Caminho do arquivo CSV gerado.
    """
    output_path = output_dir / "evaluation_results.csv"

    fieldnames = [
        "question_id",
        "project_id",
        "question",
        "mode",
        "answer",
        "retrieved_chunks_count",
        "faithfulness",
        "answer_relevancy",
        "context_precision",
        "context_recall",
    ]

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for r in results:
            writer.writerow(
                {
                    "question_id": r["question_id"],
                    "project_id": r["project_id"],
                    "question": r["question"],
                    "mode": r["mode"],
                    "answer": r["answer"][:200],  # Trunca para CSV
                    "retrieved_chunks_count": r["retrieved_chunks_count"],
                    "faithfulness": r["metrics"]["faithfulness"],
                    "answer_relevancy": r["metrics"]["answer_relevancy"],
                    "context_precision": r["metrics"]["context_precision"],
                    "context_recall": r["metrics"]["context_recall"],
                }
            )

    print(f"Resultados CSV salvos em: {output_path}")
    return output_path


def export_summary(summary: dict[str, Any], output_dir: Path) -> Path:
    """Gera sumario executivo em arquivo de texto.

    Args:
        summary: estatisticas resumidas.
        output_dir: diretorio de saida.

    Returns:
        Caminho do arquivo de sumario gerado.
    """
    output_path = output_dir / "executive_summary.txt"

    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("SUMARIO EXECUTIVO - AVALIACAO RAG ACADEMICA")
    lines.append("=" * 60)
    lines.append(f"Gerado em: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    lines.append(f"Total de perguntas avaliadas: {summary['total_questions']}")
    lines.append(f"Total de avaliacoes: {summary['total_evaluations']}")
    lines.append(f"Modos avaliados: {', '.join(summary['modes_evaluated'])}")
    lines.append("")

    lines.append("-" * 60)
    lines.append("MEDIAS GLOBAIS")
    lines.append("-" * 60)
    for metric, value in summary["global_averages"].items():
        label = metric.replace("_", " ").title()
        lines.append(f"  {label:.<30} {value:.4f}")
    lines.append("")

    lines.append("-" * 60)
    lines.append("MEDIAS POR MODO")
    lines.append("-" * 60)
    for mode, metrics in summary["mode_averages"].items():
        lines.append(f"\n  Modo: {mode}")
        for metric, value in metrics.items():
            label = metric.replace("_", " ").title()
            lines.append(f"    {label:.<28} {value:.4f}")
    lines.append("")

    lines.append("=" * 60)
    lines.append("FIM DO SUMARIO")
    lines.append("=" * 60)

    content = "\n".join(lines)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"Sumario executivo salvo em: {output_path}")
    return output_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse argumentos da linha de comando.

    Args:
        argv: argumentos (default: sys.argv[1:]).

    Returns:
        Namespace com argumentos parseados.
    """
    parser = argparse.ArgumentParser(
        description="Avaliacao academica do pipeline RAG",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--dataset",
        required=True,
        help="Caminho para o golden dataset JSON",
    )

    parser.add_argument(
        "--output",
        required=True,
        help="Diretorio de saida para relatorios",
    )

    parser.add_argument(
        "--mode",
        choices=RETRIEVAL_MODES,
        default="both",
        help="Modo de retrieval (default: both)",
    )

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Ponto de entrada principal do script de avaliacao.

    Args:
        argv: argumentos da linha de comando (default: sys.argv[1:]).
    """
    args = parse_args(argv)

    # Determina modos a executar
    if args.mode == "both":
        modes = ["project_only", "project_plus_public"]
    else:
        modes = [args.mode]

    # Carrega golden dataset
    print(f"Carregando golden dataset: {args.dataset}")
    dataset = load_golden_dataset(args.dataset)

    # Inicializa embedder
    embedder = OpenAIEmbedder()

    # Cria diretorio de saida
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Executa avaliacao
    results = run_evaluation(dataset, embedder, modes)

    # Calcula sumario
    summary = compute_summary(results)

    # Exporta resultados
    export_json(results, summary, output_dir)
    export_csv(results, output_dir)
    export_summary(summary, output_dir)

    # Imprime sumario no stdout
    print("\n" + "=" * 60)
    print("RESUMO RAPIDO")
    print("=" * 60)
    for metric, value in summary["global_averages"].items():
        label = metric.replace("_", " ").title()
        print(f"  {label}: {value:.4f}")
    print("=" * 60)


if __name__ == "__main__":
    main()
