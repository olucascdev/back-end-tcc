"""
Structured JSON logging for the Python agent service.

Configures a JSON formatter and provides a FastAPI middleware that injects
request_id and logs entry/exit of every request with duration.
Extrai project_id, document_id, session_id do body quando disponivel.
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
            "project_id",
            "document_id",
            "session_id",
            "user_id",
            "path",
            "method",
            "duration_ms",
            "status_code",
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


async def _extract_context_ids(request: Request) -> dict[str, str | None]:
    """Extrai project_id, document_id, session_id do body JSON quando disponivel.

    Faz cache no request.state para evitar leitura multipla do body.
    """
    # Retorna cache se ja extraido
    if hasattr(request.state, "_context_ids"):
        return request.state._context_ids  # type: ignore[return-value]

    context_ids: dict[str, str | None] = {
        "project_id": None,
        "document_id": None,
        "session_id": None,
    }

    # Endpoints core que contem IDs no body
    core_paths = {
        "/api/v1/process-document",
        "/api/v1/chat",
        "/api/v1/summarize-document",
        "/api/v1/compare-documents",
    }
    if request.url.path not in core_paths:
        request.state._context_ids = context_ids
        return context_ids

    try:
        body = await request.body()
        if body:
            data = json.loads(body)
            context_ids["project_id"] = data.get("project_id")
            context_ids["document_id"] = data.get("document_id")
            context_ids["session_id"] = data.get("session_id")
    except (json.JSONDecodeError, Exception):
        # Falha silenciosa — logging nao deve quebrar a requisicao
        pass

    request.state._context_ids = context_ids
    return context_ids


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware FastAPI que:
    - Injeta request_id (reutiliza do header ou gera UUID)
    - Extrai project_id, document_id, session_id do body
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

        # Extrai IDs de contexto do body
        context_ids = await _extract_context_ids(request)

        start_time = time.perf_counter()

        # Log de entrada
        extra: dict[str, Any] = {
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
        }
        if context_ids["project_id"]:
            extra["project_id"] = context_ids["project_id"]
        if context_ids["document_id"]:
            extra["document_id"] = context_ids["document_id"]
        if context_ids["session_id"]:
            extra["session_id"] = context_ids["session_id"]

        self.logger.info(
            "Request started",
            extra=extra,
        )

        response = await call_next(request)

        # Header de resposta com request_id para correlacao
        response.headers["X-Request-ID"] = request_id

        duration_ms = (time.perf_counter() - start_time) * 1000

        # Log de saida
        extra["duration_ms"] = round(duration_ms, 2)
        extra["status_code"] = response.status_code

        self.logger.info(
            "Request completed",
            extra=extra,
        )

        return response
