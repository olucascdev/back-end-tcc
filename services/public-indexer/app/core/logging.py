"""
Structured JSON logging for the public-indexer service.

Configura JSON formatter e middleware FastAPI que injeta request_id
e loga entrada/saida de cada requisicao com duracao.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

# Regex para identificar campos sensiveis em logs (chave=valor ou "chave": "valor")
_SENSITIVE_PATTERN = re.compile(
    r'((?:api_key|password|secret|token)\s*[=:]\s*)[^\s,"\'}\]]+',
    re.IGNORECASE,
)


class RedactingFilter(logging.Filter):
    """
    Filtro de log que mascara campos sensiveis.

    Substitui valores de campos como api_key, password, secret, token
    por [REDACTED] para evitar vazamento de credenciais nos logs.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        # Redact na mensagem principal
        record.msg = _SENSITIVE_PATTERN.sub(r"\1[REDACTED]", str(record.msg))

        # Redact em args se for string
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: "[REDACTED]"
                    if any(
                        s in k.lower()
                        for s in ("api_key", "password", "secret", "token")
                    )
                    else v
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    "[REDACTED]"
                    if isinstance(a, str)
                    and any(
                        s in a.lower()
                        for s in ("api_key", "password", "secret", "token")
                    )
                    else a
                    for a in record.args
                )

        return True


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
            "path",
            "method",
            "duration_ms",
            "status_code",
            "job_id",
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
    Configura o logger raiz com formatter JSON e filtro de redacao.

    Args:
        level: Nivel de log (DEBUG, INFO, WARNING, ERROR, CRITICAL).

    Returns:
        Logger configurado com handler JSON em stdout.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    # Adiciona filtro de redacao para mascarar campos sensiveis
    handler.addFilter(RedactingFilter())

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
        extra: dict[str, Any] = {
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
        }

        self.logger.info("Request started", extra=extra)

        response = await call_next(request)

        # Header de resposta com request_id para correlacao
        response.headers["X-Request-ID"] = request_id

        duration_ms = (time.perf_counter() - start_time) * 1000

        # Log de saida
        extra["duration_ms"] = round(duration_ms, 2)
        extra["status_code"] = response.status_code

        self.logger.info("Request completed", extra=extra)

        return response
