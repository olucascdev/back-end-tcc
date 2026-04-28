"""
Prometheus metrics for the Python agent service.

Exposes a /metrics endpoint and provides middleware that tracks:
- requests_total (counter with method, path, status_code labels)
- requests_duration_seconds (histogram with method, path, status_code labels)
"""

from __future__ import annotations

import time

from prometheus_client import Counter, Histogram
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

# Contador total de requisicoes
requests_total = Counter(
    "requests_total",
    "Total number of HTTP requests",
    ["method", "path", "status_code"],
)

# Histograma de duracao das requisicoes em segundos
requests_duration = Histogram(
    "requests_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path", "status_code"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware que coleta metricas Prometheus para cada requisicao."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        start_time = time.perf_counter()

        response = await call_next(request)

        duration = time.perf_counter() - start_time
        status_code = str(response.status_code)
        path = request.url.path

        # Rotas de metricas e health nao devem ser contabilizadas
        if path in ("/metrics", "/api/v1/health", "/api/v1/ready"):
            return response

        requests_total.labels(
            method=request.method,
            path=path,
            status_code=status_code,
        ).inc()

        requests_duration.labels(
            method=request.method,
            path=path,
            status_code=status_code,
        ).observe(duration)

        return response
