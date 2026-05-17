"""
Quality gate report validator.

Verifica que relatorios de benchmark e avaliacao RAG existem
e contem campos obrigatorios.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Campos obrigatorios por tipo de relatorio
BENCHMARK_REQUIRED_FIELDS = [
    "timestamp",
    "scenario",
    "requests",
    "p50_ms",
    "p95_ms",
    "p99_ms",
    "success_rate",
]

EVAL_REQUIRED_FIELDS = [
    "timestamp",
    "faithfulness",
    "relevancy",
    "precision",
    "recall",
    "sample_size",
]


def find_reports(root: Path) -> dict[str, list[Path]]:
    """Busca relatorios de benchmark e avaliacao no repositorio."""
    benchmark_reports: list[Path] = []
    eval_reports: list[Path] = []

    search_dirs = [
        root / "tools" / "benchmark",
        root / "reports",
        root / "docs",
        root / "scripts" / "benchmark",
    ]

    for search_dir in search_dirs:
        if not search_dir.is_dir():
            continue
        for f in search_dir.iterdir():
            if not f.is_file():
                continue
            name = f.name.lower()
            if f.suffix in (".json", ".md", ".txt", ".csv"):
                if any(k in name for k in ("benchmark", "performance", "load")):
                    benchmark_reports.append(f)
                if any(k in name for k in ("eval", "rag_eval", "evaluation")):
                    eval_reports.append(f)

    return {
        "benchmark": benchmark_reports,
        "evaluation": eval_reports,
    }


def validate_json_fields(filepath: Path, required: list[str]) -> tuple[bool, list[str]]:
    """Valida que arquivo JSON contem campos obrigatorios."""
    try:
        content = filepath.read_text(encoding="utf-8")
        data = json.loads(content)

        # Se for lista, valida primeiro item
        if isinstance(data, list):
            if not data:
                return False, ["Relatorio vazio (lista sem itens)"]
            data = data[0]

        missing = [f for f in required if f not in data]
        return len(missing) == 0, missing
    except json.JSONDecodeError:
        # Nao e JSON — verifica se arquivo existe e tem conteudo
        return filepath.stat().st_size > 0, []
    except Exception as e:
        return False, [str(e)]


def main() -> int:
    """Executa validacao de relatorios. Retorna 0 se tudo OK, 1 caso contrario."""
    root = Path(__file__).resolve().parent.parent.parent
    reports = find_reports(root)

    errors: list[str] = []

    # Valida relatorios de benchmark
    benchmark_files = reports["benchmark"]
    if not benchmark_files:
        errors.append("Nenhum relatorio de benchmark encontrado")
    else:
        for bf in benchmark_files:
            ok, missing = validate_json_fields(bf, BENCHMARK_REQUIRED_FIELDS)
            if not ok:
                if missing:
                    errors.append(f"{bf.name}: campos faltando: {', '.join(missing)}")
                else:
                    errors.append(f"{bf.name}: arquivo vazio ou invalido")

    # Valida relatorios de avaliacao
    eval_files = reports["evaluation"]
    if not eval_files:
        errors.append("Nenhum relatorio de avaliacao RAG encontrado")
    else:
        for ef in eval_files:
            ok, missing = validate_json_fields(ef, EVAL_REQUIRED_FIELDS)
            if not ok:
                if missing:
                    errors.append(f"{ef.name}: campos faltando: {', '.join(missing)}")
                else:
                    errors.append(f"{ef.name}: arquivo vazio ou invalido")

    if errors:
        print("Report validation FAILED:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print("Report validation PASSED")
    if benchmark_files:
        print(f"  Benchmark reports: {len(benchmark_files)} found")
    if eval_files:
        print(f"  Evaluation reports: {len(eval_files)} found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
