#!/usr/bin/env python3
"""
Benchmark comparativo: COM cache vs SEM cache.

Executa automaticamente dois testes com a mesma carga e compara resultados:
  1. Baseline: gateway com cache DESABILITADO (todas as requisicoes vao ao agente)
  2. Cached: gateway com cache HABILITADO (requisicoes repetidas sao cacheadas)

Gerencia ciclo de vida completo:
  - Inicia mock agente Python
  - Inicia mock gateway (sem cache) → executa baseline → para gateway
  - Inicia mock gateway (com cache) → executa cached → para tudo
  - Compara resultados e gera relatorio

Uso:
  python tools/benchmark/chat_compare.py
  python tools/benchmark/chat_compare.py --requests 100 --concurrency 20 --agent-delay-ms 150
  python tools/benchmark/chat_compare.py --output comparison_report.json
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------

try:
    import httpx

    _USE_HTTPX = True
except ImportError:
    _USE_HTTPX = False

# ---------------------------------------------------------------------------
# Importar benchmark baseline
# ---------------------------------------------------------------------------

# Adicionar diretorio pai ao path para importar chat_baseline
BENCHMARK_DIR = Path(__file__).parent
sys.path.insert(0, str(BENCHMARK_DIR))

from chat_baseline import DEFAULT_QUESTIONS, _percentile, run_benchmark  # noqa: E402

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent
MOCK_AGENT_SCRIPT = SCRIPT_DIR / "mock_python_agent.py"
MOCK_GATEWAY_SCRIPT = SCRIPT_DIR / "gateway_mock_with_cache.py"

AGENT_PORT = 9000
GATEWAY_PORT = 8080
AGENT_URL = f"http://localhost:{AGENT_PORT}"
GATEWAY_URL = f"http://localhost:{GATEWAY_PORT}"

# Perguntas deterministas para benchmark
# Usar subconjunto que gera repeticoes para exercitar cache
BENCHMARK_QUESTIONS = DEFAULT_QUESTIONS[:5]  # 5 perguntas, repetidas N vezes


# ---------------------------------------------------------------------------
# Gerenciamento de processos
# ---------------------------------------------------------------------------


def _wait_for_server(url: str, timeout: float = 15.0, interval: float = 0.5) -> bool:
    """Aguarda servidor ficar disponivel."""
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        try:
            if _USE_HTTPX:
                with httpx.Client(timeout=2.0) as client:
                    resp = client.get(f"{url}/health")
                    if resp.status_code == 200:
                        return True
            else:
                import urllib.request

                with urllib.request.urlopen(f"{url}/health", timeout=2.0) as resp:
                    if resp.status == 200:
                        return True
        except Exception:
            pass
        time.sleep(interval)
    return False


def _start_process(
    cmd: list[str], label: str, health_url: str
) -> subprocess.Popen | None:
    """Inicia processo e aguarda health check."""
    print(f"[compare] Iniciando {label}...")
    print(f"[compare] Comando: {' '.join(cmd)}")

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    if _wait_for_server(health_url):
        print(f"[compare] {label} pronto em {health_url}")
        return proc
    else:
        print(f"[erro] {label} nao ficou pronto em 15s")
        proc.kill()
        proc.wait()
        return None


def _stop_process(proc: subprocess.Popen | None, label: str) -> None:
    """Para processo graciosamente."""
    if proc is None:
        return
    print(f"[compare] Parando {label} (PID {proc.pid})...")
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    print(f"[compare] {label} parado")


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------


def _run_phase(
    label: str,
    gateway_url: str,
    total_requests: int,
    concurrency: int,
    project_id: str,
    session_id: str,
    questions: list[str],
) -> dict[str, Any]:
    """Executa uma fase do benchmark."""
    print(f"\n{'=' * 60}")
    print(f"  FASE: {label}")
    print(f"{'=' * 60}")

    result = run_benchmark(
        gateway_url=gateway_url,
        total_requests=total_requests,
        concurrency=concurrency,
        project_id=project_id,
        session_id=session_id,
        questions=questions,
        timeout=30.0,
    )

    # Coletar metricas do gateway
    metrics = _fetch_gateway_metrics(gateway_url)

    return {
        "label": label,
        "summary": result["summary"],
        "gateway_metrics": metrics,
    }


def _fetch_gateway_metrics(gateway_url: str) -> dict[str, Any]:
    """Busca metricas do gateway mock."""
    metrics_url = f"{gateway_url.rstrip('/')}/metrics"
    try:
        if _USE_HTTPX:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(metrics_url)
                if resp.status_code == 200:
                    return _parse_prometheus_metrics(resp.text)
        else:
            import urllib.request

            with urllib.request.urlopen(metrics_url, timeout=5.0) as resp:
                return _parse_prometheus_metrics(resp.read().decode("utf-8"))
    except Exception:
        pass
    return {}


def _parse_prometheus_metrics(text: str) -> dict[str, Any]:
    """Parse simples de metricas Prometheus."""
    metrics: dict[str, Any] = {}
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            parts = line.split()
            if len(parts) == 2:
                try:
                    metrics[parts[0]] = float(parts[1])
                except ValueError:
                    pass
    return metrics


# ---------------------------------------------------------------------------
# Comparacao e relatorio
# ---------------------------------------------------------------------------


def _compare_results(
    baseline: dict[str, Any], cached: dict[str, Any]
) -> dict[str, Any]:
    """Compara resultados baseline vs cached e calcula deltas."""
    b = baseline["summary"]
    c = cached["summary"]

    def delta_pct(old: float, new: float) -> float:
        if old == 0:
            return 0.0
        return ((new - old) / old) * 100.0

    # Calcular reducao de chamadas ao Python
    # Baseline: todas as requisicoes vao ao Python
    # Cached: apenas misses vao ao Python
    gm_cached = cached.get("gateway_metrics", {})
    total_requests = b["total_requests"]
    cache_hits = gm_cached.get("gateway_cache_hits_total", 0)
    cache_misses = gm_cached.get("gateway_cache_misses_total", 0)
    hit_ratio = cache_hits / total_requests if total_requests > 0 else 0.0
    python_call_reduction = hit_ratio * 100.0  # % de chamadas evitadas

    comparison = {
        "p50_delta_ms": round(c["latency_p50_ms"] - b["latency_p50_ms"], 2),
        "p50_delta_pct": round(delta_pct(b["latency_p50_ms"], c["latency_p50_ms"]), 2),
        "p95_delta_ms": round(c["latency_p95_ms"] - b["latency_p95_ms"], 2),
        "p95_delta_pct": round(delta_pct(b["latency_p95_ms"], c["latency_p95_ms"]), 2),
        "p99_delta_ms": round(c["latency_p99_ms"] - b["latency_p99_ms"], 2),
        "p99_delta_pct": round(delta_pct(b["latency_p99_ms"], c["latency_p99_ms"]), 2),
        "mean_delta_ms": round(c["latency_mean_ms"] - b["latency_mean_ms"], 2),
        "mean_delta_pct": round(
            delta_pct(b["latency_mean_ms"], c["latency_mean_ms"]), 2
        ),
        "rps_delta": round(c["requests_per_second"] - b["requests_per_second"], 2),
        "rps_delta_pct": round(
            delta_pct(b["requests_per_second"], c["requests_per_second"]), 2
        ),
        "error_rate_baseline": b["error_rate"],
        "error_rate_cached": c["error_rate"],
        "cache_hits": int(cache_hits),
        "cache_misses": int(cache_misses),
        "cache_hit_ratio": round(hit_ratio, 4),
        "python_call_reduction_pct": round(python_call_reduction, 2),
    }

    return comparison


def _print_comparison_table(
    baseline: dict[str, Any],
    cached: dict[str, Any],
    comparison: dict[str, Any],
) -> None:
    """Imprime tabela comparativa em markdown."""
    b = baseline["summary"]
    c = cached["summary"]

    sep = "=" * 72
    print(f"\n{sep}")
    print("  COMPARACAO DE PERFORMANCE: SEM CACHE vs COM CACHE")
    print(sep)
    print()

    # Tabela principal
    header = f"{'Metrica':<30} {'Sem Cache':>14} {'Com Cache':>14} {'Delta':>12}"
    print(header)
    print("-" * 72)

    rows = [
        (
            "Latencia p50 (ms)",
            f"{b['latency_p50_ms']:.2f}",
            f"{c['latency_p50_ms']:.2f}",
            f"{comparison['p50_delta_pct']:+.1f}%",
        ),
        (
            "Latencia p95 (ms)",
            f"{b['latency_p95_ms']:.2f}",
            f"{c['latency_p95_ms']:.2f}",
            f"{comparison['p95_delta_pct']:+.1f}%",
        ),
        (
            "Latencia p99 (ms)",
            f"{b['latency_p99_ms']:.2f}",
            f"{c['latency_p99_ms']:.2f}",
            f"{comparison['p99_delta_pct']:+.1f}%",
        ),
        (
            "Latencia media (ms)",
            f"{b['latency_mean_ms']:.2f}",
            f"{c['latency_mean_ms']:.2f}",
            f"{comparison['mean_delta_pct']:+.1f}%",
        ),
        (
            "Requests/sec",
            f"{b['requests_per_second']:.2f}",
            f"{c['requests_per_second']:.2f}",
            f"{comparison['rps_delta_pct']:+.1f}%",
        ),
        (
            "Taxa de erro",
            f"{b['error_rate']:.2%}",
            f"{c['error_rate']:.2%}",
            f"{c['error_rate'] - b['error_rate']:+.2%}",
        ),
    ]

    for label, baseline_val, cached_val, delta in rows:
        print(f"{label:<30} {baseline_val:>14} {cached_val:>14} {delta:>12}")

    print()
    print("-" * 72)
    print("  ESTATISTICAS DE CACHE")
    print("-" * 72)

    cache_rows = [
        ("Cache hits", str(comparison["cache_hits"])),
        ("Cache misses", str(comparison["cache_misses"])),
        ("Cache hit ratio", f"{comparison['cache_hit_ratio']:.2%}"),
        (
            "Reducao chamadas Python",
            f"{comparison['python_call_reduction_pct']:.1f}%",
        ),
    ]

    for label, val in cache_rows:
        print(f"  {label:<30} {val}")

    print(sep)

    # Analise
    print()
    print("  ANALISE:")
    p95_improved = comparison["p95_delta_pct"] < 0
    python_reduced = comparison["python_call_reduction_pct"] > 30
    hit_ratio_ok = comparison["cache_hit_ratio"] >= 0.40

    if p95_improved:
        print(
            f"  [OK] p95 reduziu {abs(comparison['p95_delta_pct']):.1f}% "
            f"(meta: >=25% reducao)"
        )
    else:
        print(
            f"  [!!] p95 aumentou {comparison['p95_delta_pct']:.1f}% "
            f"(meta: >=25% reducao)"
        )

    if python_reduced:
        print(
            f"  [OK] Chamadas Python reduzidas {comparison['python_call_reduction_pct']:.1f}% "
            f"(meta: >=30%)"
        )
    else:
        print(
            f"  [!!] Chamadas Python reduzidas {comparison['python_call_reduction_pct']:.1f}% "
            f"(meta: >=30%)"
        )

    if hit_ratio_ok:
        print(
            f"  [OK] Cache hit ratio {comparison['cache_hit_ratio']:.2%} (meta: >=40%)"
        )
    else:
        print(
            f"  [!!] Cache hit ratio {comparison['cache_hit_ratio']:.2%} (meta: >=40%)"
        )

    print(sep)


# ---------------------------------------------------------------------------
# Orquestracao principal
# ---------------------------------------------------------------------------


def run_comparison(
    total_requests: int = 50,
    concurrency: int = 10,
    agent_delay_ms: int = 150,
    output_path: str | None = None,
) -> dict[str, Any]:
    """
    Executa benchmark comparativo completo.

    Retorna dicionario com resultados de ambas as fases e comparacao.
    """
    project_id = "benchmark-compare-000000000000"
    session_id = "compare-session"

    # Usar perguntas que se repetem para exercitar cache
    # 5 perguntas repetidas = alta taxa de hit no cache
    questions = BENCHMARK_QUESTIONS

    agent_proc = None
    gateway_proc = None

    try:
        # ---------------------------------------------------------------
        # 1. Iniciar mock agente Python
        # ---------------------------------------------------------------
        print("\n[compare] === INICIANDO BENCHMARK COMPARATIVO ===")
        print(f"[compare] Requests: {total_requests}, Concorrencia: {concurrency}")
        print(f"[compare] Agent delay: {agent_delay_ms}ms")
        print(f"[compare] Perguntas: {len(questions)} (repetidas)")

        agent_proc = _start_process(
            cmd=[
                sys.executable,
                str(MOCK_AGENT_SCRIPT),
                "--port",
                str(AGENT_PORT),
                "--delay-ms",
                str(agent_delay_ms),
            ],
            label="Mock Python Agent",
            health_url=AGENT_URL,
        )
        if agent_proc is None:
            print("[erro] Falha ao iniciar mock agente. Abortando.")
            return {"error": "Failed to start mock agent"}

        # ---------------------------------------------------------------
        # 2. Fase 1: Baseline (cache OFF)
        # ---------------------------------------------------------------
        gateway_proc = _start_process(
            cmd=[
                sys.executable,
                str(MOCK_GATEWAY_SCRIPT),
                "--port",
                str(GATEWAY_PORT),
                "--agent-url",
                AGENT_URL,
                "--cache-enabled",
                "false",
            ],
            label="Mock Gateway (cache OFF)",
            health_url=GATEWAY_URL,
        )
        if gateway_proc is None:
            print("[erro] Falha ao iniciar gateway baseline. Abortando.")
            return {"error": "Failed to start baseline gateway"}

        baseline_result = _run_phase(
            label="baseline_sem_cache",
            gateway_url=GATEWAY_URL,
            total_requests=total_requests,
            concurrency=concurrency,
            project_id=project_id,
            session_id=session_id,
            questions=questions,
        )

        _stop_process(gateway_proc, "Mock Gateway (cache OFF)")
        gateway_proc = None

        # Pequena pausa para liberar porta
        time.sleep(1)

        # ---------------------------------------------------------------
        # 3. Fase 2: Cached (cache ON)
        # ---------------------------------------------------------------
        gateway_proc = _start_process(
            cmd=[
                sys.executable,
                str(MOCK_GATEWAY_SCRIPT),
                "--port",
                str(GATEWAY_PORT),
                "--agent-url",
                AGENT_URL,
                "--cache-enabled",
                "true",
            ],
            label="Mock Gateway (cache ON)",
            health_url=GATEWAY_URL,
        )
        if gateway_proc is None:
            print("[erro] Falha ao iniciar gateway com cache. Abortando.")
            return {"error": "Failed to start cached gateway"}

        cached_result = _run_phase(
            label="cached_com_cache",
            gateway_url=GATEWAY_URL,
            total_requests=total_requests,
            concurrency=concurrency,
            project_id=project_id,
            session_id=session_id,
            questions=questions,
        )

        # ---------------------------------------------------------------
        # 4. Comparar resultados
        # ---------------------------------------------------------------
        comparison = _compare_results(baseline_result, cached_result)

        # Montar relatorio final
        report = {
            "metadata": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "total_requests": total_requests,
                "concurrency": concurrency,
                "agent_delay_ms": agent_delay_ms,
                "questions_count": len(questions),
                "questions": questions,
            },
            "baseline": baseline_result,
            "cached": cached_result,
            "comparison": comparison,
        }

        # Imprimir tabela comparativa
        _print_comparison_table(baseline_result, cached_result, comparison)

        # Salvar relatorio
        if output_path:
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, default=str)
            print(f"\n[compare] Relatorio salvo em {output_file}")

        return report

    finally:
        # Limpar processos
        _stop_process(gateway_proc, "Mock Gateway")
        _stop_process(agent_proc, "Mock Python Agent")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark comparativo: COM cache vs SEM cache",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  # Execucao padrao (50 requests, 10 concorrentes, 150ms delay)
  python chat_compare.py

  # Carga maior
  python chat_compare.py --requests 200 --concurrency 20

  # Delay maior no agente (simular agente mais lento)
  python chat_compare.py --agent-delay-ms 300

  # Salvar relatorio
  python chat_compare.py --output comparison_report.json
""",
    )
    parser.add_argument(
        "--requests",
        type=int,
        default=50,
        help="Numero total de requisicoes por fase (default: 50)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=10,
        help="Numero de requisicoes concorrentes (default: 10)",
    )
    parser.add_argument(
        "--agent-delay-ms",
        type=int,
        default=150,
        help="Delay do agente Python em ms (default: 150)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Caminho para salvar relatorio JSON comparativo",
    )

    args = parser.parse_args()

    run_comparison(
        total_requests=args.requests,
        concurrency=args.concurrency,
        agent_delay_ms=args.agent_delay_ms,
        output_path=args.output,
    )


if __name__ == "__main__":
    main()
