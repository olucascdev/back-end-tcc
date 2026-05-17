#!/usr/bin/env python3
"""
Mock do agente Python para benchmark.

Simula o endpoint POST /chat do agente Python com resposta fixa
no formato exato do contrato v1 (ChatResponse).

Uso:
  python tools/benchmark/mock_python_agent.py
  python tools/benchmark/mock_python_agent.py --port 9000 --delay-ms 200

O mock loga cada requisicao recebida para verificacao.
"""

import argparse
import asyncio
import logging
import sys
from datetime import UTC, datetime

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [mock-agent] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schemas (espelham contracts_v1.py exatamente)
# ---------------------------------------------------------------------------

try:
    from pydantic import BaseModel, Field
except ImportError:
    logger.error("Pydantic nao instalado. Instale: pip install pydantic")
    sys.exit(1)


class Source(BaseModel):
    document: str
    page: int
    section: str | None = None
    score: float


class ChatRequest(BaseModel):
    project_id: str  # UUID como string para simplicidade
    session_id: str
    message: str
    filters: dict | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]
    session_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ---------------------------------------------------------------------------
# FastAPI mock
# ---------------------------------------------------------------------------


def create_app(delay_ms: int = 0) -> "FastAPI":
    """Cria aplicacao FastAPI mock com delay configuravel."""
    try:
        from fastapi import FastAPI
    except ImportError:
        logger.error("FastAPI nao instalado. Instale: pip install fastapi uvicorn")
        sys.exit(1)

    app = FastAPI(title="Mock Python Agent", version="1.0.0")

    # -----------------------------------------------------------------------
    # Contador de requests
    # -----------------------------------------------------------------------

    request_count = 0

    # -----------------------------------------------------------------------
    # Endpoints
    # -----------------------------------------------------------------------

    @app.post("/chat", response_model=ChatResponse)
    async def chat(req: ChatRequest) -> ChatResponse:
        """Endpoint mock de chat RAG."""
        nonlocal request_count
        request_count += 1

        logger.info(
            "Chat request #%d: project_id=%s, session_id=%s, message=%r",
            request_count,
            req.project_id,
            req.session_id,
            req.message[:80],
        )

        # Simular latencia de processamento
        if delay_ms > 0:
            await asyncio.sleep(delay_ms / 1000.0)

        # Resposta fixa com formato realista
        return ChatResponse(
            answer=(
                "This is a mock response from the Python agent. "
                "In production, this would contain a RAG-generated answer "
                "based on document context retrieved from pgvector. "
                f"Your question was: '{req.message}'"
            ),
            sources=[
                Source(
                    document="mock_document.pdf",
                    page=1,
                    section="Introduction",
                    score=0.92,
                ),
                Source(
                    document="mock_document.pdf",
                    page=3,
                    section="Methodology",
                    score=0.85,
                ),
            ],
            session_id=req.session_id,
        )

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Health check do mock."""
        return {"status": "ok", "service": "mock-python-agent"}

    @app.get("/metrics")
    async def metrics() -> str:
        """Metricas simples em formato Prometheus."""
        return f"# HELP mock_chat_requests_total Total mock chat requests\n# TYPE mock_chat_requests_total counter\nmock_chat_requests_total {request_count}\n"

    @app.get("/request-log")
    async def request_log() -> dict[str, int]:
        """Retorna contador de requests recebidos."""
        return {"total_requests": request_count}

    return app


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mock do agente Python para benchmark de performance",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  # Iniciar mock com delay de 150ms (simula latencia realista)
  python mock_python_agent.py --port 9000 --delay-ms 150

  # Iniciar mock sem delay (resposta instantanea)
  python mock_python_agent.py --port 9000

  # Para usar com o benchmark:
  # 1. Inicie o mock: python mock_python_agent.py --port 9000 --delay-ms 150
  # 2. Configure o gateway para apontar para http://localhost:9000
  # 3. Execute o benchmark: python chat_baseline.py --url http://localhost:8080
""",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=9000,
        help="Porta do servidor mock (default: 9000)",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host do servidor mock (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--delay-ms",
        type=int,
        default=0,
        help="Delay artificial em milissegundos por requisicao (default: 0)",
    )

    args = parser.parse_args()

    logger.info(
        "Iniciando mock Python agent na porta %d com delay %dms",
        args.port,
        args.delay_ms,
    )

    app = create_app(delay_ms=args.delay_ms)

    try:
        import uvicorn

        uvicorn.run(
            app,
            host=args.host,
            port=args.port,
            log_level="info",
        )
    except ImportError:
        logger.error("Uvicorn nao instalado. Instale: pip install uvicorn")
        sys.exit(1)


if __name__ == "__main__":
    main()
