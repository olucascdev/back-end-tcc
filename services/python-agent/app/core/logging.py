"""
Structured JSON logging for the Python agent service.

Configures a JSON formatter and provides a FastAPI middleware that injects
request_id and logs entry/exit of every request with duration.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class JSONFormatter(logging.Formatter):
    """Formatter que produz linhas JSON para consumo por sistemas de log."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "message": record.getMessage(),
        }

        # Campos extras injetados via logging adapter ou extra=
        for key in (
            "request_id",
            "project_id",
            "user_id",
            "path",
            "method",
            "duration_ms",
        ):
            value = getattr(record, key, None)
            if value is not None:
                log_entry[key] = value

        # Inclui traceback se houver excecao
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> logging.Logger:
    """
    Configura o logger raiz com formatter JSON.

    Args:
        level: Nivel de log (DEBUG, INFO, WARNING, ERROR, CRITICAL).

    Returns:
        Logger configurado com handler JSON em stdout.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    # Limpa handlers existentes para evitar duplicacao
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    return root_logger


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware FastAPI que:
    - Injeta request_id (reutiliza do header ou gera UUID)
    - Loga entrada e saida de cada request com duracao em ms
    """

    def __init__(self, app: Any, logger: logging.Logger | None = None) -> None:
        super().__init__(app)
        self.logger = logger or logging.getLogger()

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

        # Disponibiliza request_id no scope para handlers downstream
        request.state.request_id = request_id

        start_time = time.perf_counter()

        # Log de entrada
        self.logger.info(
            "Request started",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
            },
        )

        response = await call_next(request)

        # Header de resposta com request_id para correlacao
        response.headers["X-Request-ID"] = request_id

        duration_ms = (time.perf_counter() - start_time) * 1000

        # Log de saida
        self.logger.info(
            "Request completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "duration_ms": round(duration_ms, 2),
            },
        )

        return response
