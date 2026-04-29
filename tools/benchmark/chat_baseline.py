#!/usr/bin/env python3
"""
Benchmark de linha de base para o endpoint POST /api/v1/chat.

Modos de operacao:
  - live: contra gateway + agente Python reais
  - mock: contra gateway apontando para mock_python_agent.py

Dependencias: httpx (ja instalado no ambiente).
Fallback para urllib.request se httpx nao disponivel.

Uso:
  python tools/benchmark/chat_baseline.py --url http://localhost:8080 --requests 50 --concurrency 10
  python tools/benchmark/chat_baseline.py --url http://localhost:8080 --requests 100 --concurrency 20 --report report.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

# ---------------------------------------------------------------------------
# HTTP client: prefer httpx, fallback to urllib
# ---------------------------------------------------------------------------

try:
    import httpx

    _USE_HTTPX = True
except ImportError:
    _USE_HTTPX = False

# ---------------------------------------------------------------------------
# Perguntas padrao (deterministicas, sem aleatoriedade)
# ---------------------------------------------------------------------------

DEFAULT_QUESTIONS: list[str] = [
    "What is the main objective of this research?",
    "Describe the methodology used in the document.",
    "What are the key findings and results?",
    "How does this work compare to related literature?",
    "What limitations does the author acknowledge?",
    "Explain the theoretical framework applied.",
    "What future work does the author suggest?",
    "Summarize the conclusions of this study.",
    "What data sources were used for analysis?",
    "How were the research questions formulated?",
]


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _post_json(
    url: str, payload: dict[str, Any], timeout: float = 30.0
) -> tuple[float, int, str]:
    """
    Envia POST JSON e retorna (latencia_s, status_code, body_str).
    """
    if _USE_HTTPX:
        return _post_httpx(url, payload, timeout)
    return _post_urllib(url, payload, timeout)


def _post_httpx(
    url: str, payload: dict[str, Any], timeout: float
) -> tuple[float, int, str]:
    start = time.perf_counter()
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json=payload)
            elapsed = time.perf_counter() - start
            return elapsed, resp.status_code, resp.text
    except Exception as exc:
        elapsed = time.perf_counter() - start
        return elapsed, 0, str(exc)


def _post_urllib(
    url: str, payload: dict[str, Any], timeout: float
) -> tuple[float, int, str]:
    import urllib.error
    import urllib.request

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            elapsed = time.perf_counter() - start
            body = resp.read().decode("utf-8")
            return elapsed, resp.status, body
    except urllib.error.HTTPError as exc:
        elapsed = time.perf_counter() - start
        body = exc.read().decode("utf-8", errors="replace")
        return elapsed, exc.code, body
    except Exception as exc:
        elapsed = time.perf_counter() - start
        return elapsed, 0, str(exc)


def _fetch_metrics(metrics_url: str) -> dict[str, Any]:
    """Busca snapshot das metricas Prometheus do gateway."""
    if _USE_HTTPX:
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(metrics_url)
                if resp.status_code == 200:
                    return {"raw": resp.text, "status": 200}
        except Exception:
            pass
    else:
        import urllib.request

        try:
            with urllib.request.urlopen(metrics_url, timeout=5.0) as resp:
                return {"raw": resp.read().decode("utf-8"), "status": 200}
        except Exception:
            pass
    return {"raw": "", "status": 0}


# ---------------------------------------------------------------------------
# Percentil
# ---------------------------------------------------------------------------


def _percentile(sorted_data: list[float], p: float) -> float:
    """Calcula percentil p (0-100) de dados ordenados."""
    if not sorted_data:
        return 0.0
    k = (len(sorted_data) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_data[int(k)]
    d0 = sorted_data[int(f)] * (c - k)
    d1 = sorted_data[int(c)] * (k - f)
    return d0 + d1


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------


def run_benchmark(
    gateway_url: str,
    total_requests: int,
    concurrency: int,
    project_id: str,
    session_id: str,
    questions: list[str] | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """
    Executa benchmark concorrente contra o gateway.

    Retorna dicionario com latencias, erros e resumo.
    """
    if questions is None:
        questions = DEFAULT_QUESTIONS

    chat_url = f"{gateway_url.rstrip('/')}/api/v1/chat"
    latencies: list[float] = []
    status_codes: list[int] = []
    errors: list[str] = []

    def _make_request(idx: int) -> tuple[float, int, str | None]:
        q = questions[idx % len(questions)]
        payload = {
            "project_id": project_id,
            "session_id": session_id,
            "message": q,
        }
        elapsed, status, body = _post_json(chat_url, payload, timeout=timeout)
        err = None
        if status < 200 or status >= 300:
            err = f"status={status} body={body[:200]}"
        return elapsed, status, err

    print(
        f"[benchmark] Iniciando: {total_requests} requests, concorrencia={concurrency}"
    )
    print(f"[benchmark] URL: {chat_url}")
    print(f"[benchmark] project_id={project_id}, session_id={session_id}")

    wall_start = time.perf_counter()

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {pool.submit(_make_request, i): i for i in range(total_requests)}
        for future in as_completed(futures):
            elapsed, status, err = future.result()
            latencies.append(elapsed)
            status_codes.append(status)
            if err:
                errors.append(err)

    wall_duration = time.perf_counter() - wall_start

    # Calcular estatisticas
    latencies_sorted = sorted(latencies)
    p50 = _percentile(latencies_sorted, 50)
    p95 = _percentile(latencies_sorted, 95)
    p99 = _percentile(latencies_sorted, 99)
    mean_lat = statistics.mean(latencies) if latencies else 0.0
    error_count = sum(1 for s in status_codes if s < 200 or s >= 300)
    error_rate = error_count / total_requests if total_requests > 0 else 0.0

    summary = {
        "total_requests": total_requests,
        "successful_requests": total_requests - error_count,
        "failed_requests": error_count,
        "error_rate": round(error_rate, 4),
        "duration_seconds": round(wall_duration, 3),
        "requests_per_second": round(total_requests / wall_duration, 2)
        if wall_duration > 0
        else 0.0,
        "latency_p50_ms": round(p50 * 1000, 2),
        "latency_p95_ms": round(p95 * 1000, 2),
        "latency_p99_ms": round(p99 * 1000, 2),
        "latency_mean_ms": round(mean_lat * 1000, 2),
        "latency_min_ms": round(min(latencies) * 1000, 2) if latencies else 0.0,
        "latency_max_ms": round(max(latencies) * 1000, 2) if latencies else 0.0,
    }

    return {
        "latencies": latencies,
        "status_codes": status_codes,
        "errors": errors,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark de linha de base para POST /api/v1/chat",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  # Modo live (gateway + Python agent reais)
  python chat_baseline.py --url http://localhost:8080 --requests 50 --concurrency 10

  # Modo mock (gateway apontando para mock_python_agent.py)
  # 1. Inicie o mock: python mock_python_agent.py --port 9000 --delay-ms 150
  # 2. Execute o benchmark:
  python chat_baseline.py --url http://localhost:8080 --requests 100 --concurrency 20

  # Com arquivo de perguntas customizado
  python chat_baseline.py --url http://localhost:8080 --requests 30 --questions-file questions.json

  # Salvar relatorio JSON
  python chat_baseline.py --url http://localhost:8080 --report baseline_report.json
""",
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8080",
        help="URL base do gateway Go (default: http://localhost:8080)",
    )
    parser.add_argument(
        "--requests",
        type=int,
        default=50,
        help="Numero total de requisicoes (default: 50)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=10,
        help="Numero de requisicoes concorrentes (default: 10)",
    )
    parser.add_argument(
        "--project-id",
        default=str(uuid4()),
        help="UUID do projeto (default: gerado aleatoriamente)",
    )
    parser.add_argument(
        "--session-id",
        default=f"bench-session-{uuid4().hex[:8]}",
        help="ID da sessao (default: gerado aleatoriamente)",
    )
    parser.add_argument(
        "--questions-file",
        default=None,
        help="Caminho para arquivo JSON com lista de perguntas (fallback: perguntas padrao)",
    )
    parser.add_argument(
        "--report",
        default=None,
        help="Caminho para salvar relatorio JSON completo",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Timeout por requisicao em segundos (default: 30)",
    )
    parser.add_argument(
        "--metrics-url",
        default=None,
        help="URL das metricas Prometheus do gateway (default: {--url}/metrics)",
    )

    args = parser.parse_args()

    # Carregar perguntas
    questions: list[str] | None = None
    if args.questions_file:
        try:
            with open(args.questions_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    questions = [str(q) for q in data if q]
                elif isinstance(data, dict) and "questions" in data:
                    questions = [str(q) for q in data["questions"] if q]
                else:
                    print(
                        f"[erro] Formato invalido em {args.questions_file}",
                        file=sys.stderr,
                    )
                    sys.exit(1)
            print(
                f"[benchmark] Carregadas {len(questions)} perguntas de {args.questions_file}"
            )
        except Exception as exc:
            print(f"[erro] Falha ao ler {args.questions_file}: {exc}", file=sys.stderr)
            sys.exit(1)

    metrics_url = args.metrics_url or f"{args.url.rstrip('/')}/metrics"

    # Snapshot metricas antes
    print(f"[benchmark] Coletando metricas antes do teste: {metrics_url}")
    metrics_before = _fetch_metrics(metrics_url)

    # Executar benchmark
    result = run_benchmark(
        gateway_url=args.url,
        total_requests=args.requests,
        concurrency=args.concurrency,
        project_id=args.project_id,
        session_id=args.session_id,
        questions=questions,
        timeout=args.timeout,
    )

    # Snapshot metricas depois
    print(f"[benchmark] Coletando metricas apos o teste: {metrics_url}")
    metrics_after = _fetch_metrics(metrics_url)

    # Delta de metricas (requests_total para chat)
    metrics_delta: dict[str, Any] = {}
    if metrics_before["status"] == 200 and metrics_after["status"] == 200:
        delta = _compute_metrics_delta(metrics_before["raw"], metrics_after["raw"])
        metrics_delta = delta

    # Montar relatorio
    report = {
        "config": {
            "url": args.url,
            "total_requests": args.requests,
            "concurrency": args.concurrency,
            "project_id": args.project_id,
            "session_id": args.session_id,
            "timeout": args.timeout,
            "questions_file": args.questions_file,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        "summary": result["summary"],
        "raw_latencies": result["latencies"],
        "metrics_before": metrics_before,
        "metrics_after": metrics_after,
        "metrics_delta": metrics_delta,
    }

    # Salvar relatorio
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"[benchmark] Relatorio salvo em {args.report}")

    # Imprimir resumo legivel
    _print_summary(result["summary"], metrics_delta)


def _compute_metrics_delta(before_raw: str, after_raw: str) -> dict[str, Any]:
    """
    Calcula delta de metricas Prometheus entre dois snapshots.
    Foca em requests_total para o endpoint de chat.
    """

    def _parse_counter(raw: str) -> dict[str, int]:
        counters: dict[str, int] = {}
        for line in raw.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "requests_total" in line:
                parts = line.split()
                if len(parts) == 2:
                    try:
                        counters[parts[0]] = int(parts[1])
                    except ValueError:
                        pass
        return counters

    before = _parse_counter(before_raw)
    after = _parse_counter(after_raw)

    delta: dict[str, int] = {}
    all_keys = set(before.keys()) | set(after.keys())
    for key in sorted(all_keys):
        d = after.get(key, 0) - before.get(key, 0)
        if d > 0:
            delta[key] = d

    return delta


def _print_summary(summary: dict[str, Any], metrics_delta: dict[str, Any]) -> None:
    """Imprime resumo legivel do benchmark."""
    sep = "=" * 60
    print(f"\n{sep}")
    print("  BENCHMARK RESULTADO")
    print(sep)
    print(f"  Requisicoes totais:     {summary['total_requests']}")
    print(f"  Sucesso:                {summary['successful_requests']}")
    print(f"  Falhas:                 {summary['failed_requests']}")
    print(f"  Taxa de erro:           {summary['error_rate']:.2%}")
    print(f"  Duracao total:          {summary['duration_seconds']:.3f}s")
    print(f"  Requisicoes/segundo:    {summary['requests_per_second']:.2f}")
    print(f"  Latencia p50:           {summary['latency_p50_ms']:.2f}ms")
    print(f"  Latencia p95:           {summary['latency_p95_ms']:.2f}ms")
    print(f"  Latencia p99:           {summary['latency_p99_ms']:.2f}ms")
    print(f"  Latencia media:         {summary['latency_mean_ms']:.2f}ms")
    print(f"  Latencia min:           {summary['latency_min_ms']:.2f}ms")
    print(f"  Latencia max:           {summary['latency_max_ms']:.2f}ms")
    if metrics_delta:
        print(f"\n  Delta de metricas (gateway):")
        for key, val in metrics_delta.items():
            print(f"    {key}: +{val}")
    print(sep)


if __name__ == "__main__":
    main()
