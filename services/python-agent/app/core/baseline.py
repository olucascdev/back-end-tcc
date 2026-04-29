"""
Simple benchmark runner for the python-agent chat endpoint.

Measures p50/p95/p99 latency, throughput (req/s), and error rate
against local infrastructure (PostgreSQL+pgvector, Redis).
"""

from __future__ import annotations

import json
import logging
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib import request, error

logger = logging.getLogger(__name__)


@dataclass
class BenchmarkResult:
    """Aggregated benchmark metrics."""

    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    latencies_ms: list[float] = field(default_factory=list)

    @property
    def error_rate(self) -> float:
        """Fraction of failed requests."""
        if self.total_requests == 0:
            return 0.0
        return self.failed_requests / self.total_requests

    @property
    def throughput(self) -> float:
        """Requests per second."""
        if not self.latencies_ms:
            return 0.0
        total_time_s = sum(self.latencies_ms) / 1000.0
        return self.successful_requests / total_time_s if total_time_s > 0 else 0.0

    def percentile(self, p: float) -> float:
        """Compute p-th percentile of latencies."""
        if not self.latencies_ms:
            return 0.0
        sorted_latencies = sorted(self.latencies_ms)
        idx = int(len(sorted_latencies) * p / 100.0)
        idx = min(idx, len(sorted_latencies) - 1)
        return sorted_latencies[idx]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON output."""
        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "error_rate": round(self.error_rate, 4),
            "throughput_req_per_s": round(self.throughput, 2),
            "latency_p50_ms": round(self.percentile(50), 2),
            "latency_p95_ms": round(self.percentile(95), 2),
            "latency_p99_ms": round(self.percentile(99), 2),
            "latency_mean_ms": round(statistics.mean(self.latencies_ms), 2)
            if self.latencies_ms
            else 0.0,
            "latency_min_ms": round(min(self.latencies_ms), 2)
            if self.latencies_ms
            else 0.0,
            "latency_max_ms": round(max(self.latencies_ms), 2)
            if self.latencies_ms
            else 0.0,
        }


class BenchmarkRunner:
    """Runs HTTP benchmark against the chat endpoint."""

    def __init__(
        self,
        base_url: str = "http://localhost:8001",
        project_id: str = "00000000-0000-0000-0000-000000000000",
        session_id: str = "benchmark-session",
        message: str = "Qual e o objetivo deste documento?",
        num_requests: int = 50,
        concurrency: int = 1,
    ) -> None:
        self.base_url = base_url
        self.project_id = project_id
        self.session_id = session_id
        self.message = message
        self.num_requests = num_requests
        self.concurrency = concurrency

    def _send_request(self, request_id: int) -> tuple[bool, float]:
        """Send single POST /api/v1/chat request. Returns (success, latency_ms)."""
        payload = json.dumps(
            {
                "project_id": self.project_id,
                "session_id": f"{self.session_id}-{request_id}",
                "message": self.message,
            }
        ).encode("utf-8")

        req = request.Request(
            f"{self.base_url}/api/v1/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        start = time.perf_counter()
        try:
            with request.urlopen(req, timeout=30) as resp:
                resp.read()
                latency_ms = (time.perf_counter() - start) * 1000
                return True, latency_ms
        except (error.URLError, error.HTTPError, TimeoutError) as exc:
            latency_ms = (time.perf_counter() - start) * 1000
            logger.warning("Request %d failed: %s", request_id, exc)
            return False, latency_ms

    def run(self) -> BenchmarkResult:
        """Execute benchmark and return aggregated results."""
        result = BenchmarkResult()
        logger.info(
            "Starting benchmark: %d requests against %s",
            self.num_requests,
            self.base_url,
        )

        for i in range(self.num_requests):
            success, latency_ms = self._send_request(i)
            result.total_requests += 1
            result.latencies_ms.append(latency_ms)
            if success:
                result.successful_requests += 1
            else:
                result.failed_requests += 1

        logger.info(
            "Benchmark complete: p50=%.2fms, p95=%.2fms, p99=%.2fms, "
            "throughput=%.2f req/s, error_rate=%.2f%%",
            result.percentile(50),
            result.percentile(95),
            result.percentile(99),
            result.throughput,
            result.error_rate * 100,
        )
        return result

    def run_and_save(self, output_path: str = "reports/baseline_phase6.json") -> dict:
        """Run benchmark and save JSON report."""
        result = self.run()
        report = {
            "benchmark": "phase6_preflight_baseline",
            "endpoint": "POST /api/v1/chat",
            "config": {
                "base_url": self.base_url,
                "num_requests": self.num_requests,
                "concurrency": self.concurrency,
                "message": self.message,
            },
            "metrics": result.to_dict(),
        }

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)

        logger.info("Report saved to %s", output_path)
        return report


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    runner = BenchmarkRunner(
        base_url="http://localhost:8001",
        num_requests=50,
    )
    report = runner.run_and_save()
    print(json.dumps(report, indent=2))
