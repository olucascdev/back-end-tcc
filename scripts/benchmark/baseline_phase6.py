#!/usr/bin/env python3
"""
Phase 6 preflight baseline benchmark.

Measures current baseline of the chat endpoint (python-agent POST /chat):
- p50/p95/p99 latency
- throughput (req/s)
- error rate

Runs against local infrastructure (PostgreSQL+pgvector, Redis).
Outputs JSON report to reports/baseline_phase6.json.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

# Add project root to path so we can import the baseline module
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.baseline import BenchmarkRunner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    """Run baseline benchmark and save report."""
    output_path = PROJECT_ROOT.parent / "reports" / "baseline_phase6.json"

    runner = BenchmarkRunner(
        base_url="http://localhost:8001",
        num_requests=50,
        concurrency=1,
    )

    logger.info("Running Phase 6 preflight baseline...")
    report = runner.run_and_save(str(output_path))

    metrics = report["metrics"]
    print("\n=== Phase 6 Baseline Report ===")
    print(f"  Total requests:    {metrics['total_requests']}")
    print(f"  Successful:        {metrics['successful_requests']}")
    print(f"  Failed:            {metrics['failed_requests']}")
    print(f"  Error rate:        {metrics['error_rate']:.2%}")
    print(f"  Throughput:        {metrics['throughput_req_per_s']:.2f} req/s")
    print(f"  Latency p50:       {metrics['latency_p50_ms']:.2f} ms")
    print(f"  Latency p95:       {metrics['latency_p95_ms']:.2f} ms")
    print(f"  Latency p99:       {metrics['latency_p99_ms']:.2f} ms")
    print(f"  Latency mean:      {metrics['latency_mean_ms']:.2f} ms")
    print(f"  Latency min:       {metrics['latency_min_ms']:.2f} ms")
    print(f"  Latency max:       {metrics['latency_max_ms']:.2f} ms")
    print(f"\nReport saved to: {output_path}")


if __name__ == "__main__":
    main()
