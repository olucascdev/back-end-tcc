#!/usr/bin/env python3
"""
Mock do gateway Go que simula comportamento de cache semantico.

Este mock replica o comportamento do gateway Go para fins de benchmark,
permitindo comparar performance COM e SEM cache sem alterar o codigo real.

Comportamento controlado por env var CACHE_ENABLED ou flag --cache-enabled:
  - CACHE OFF: encaminha todas as requisicoes ao agente Python (baseline)
  - CACHE ON: implementa cache semantico em memoria com normalizacao de pergunta

Contrato: espelha exatamente ChatRequest/ChatResponse do contracts_v1.py.

Uso:
  python tools/benchmark/gateway_mock_with_cache.py
  python tools/benchmark/gateway_mock_with_cache.py --port 8080 --cache-enabled false
  CACHE_ENABLED=false python tools/benchmark/gateway_mock_with_cache.py --port 8080
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import os
import re
import string
import time
from datetime import UTC, datetime
from typing import Any

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [mock-gateway] %(levelname)s %(message)s",
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
    raise SystemExit(1)


class Source(BaseModel):
    document: str
    page: int
    section: str | None = None
    score: float


class ChatRequest(BaseModel):
    project_id: str
    session_id: str
    message: str
    filters: dict | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]
    session_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ---------------------------------------------------------------------------
# Normalizacao de pergunta (replica Go NormalizeQuestion)
# ---------------------------------------------------------------------------

# Tabela de traducao para remover pontuacao
_PUNCTUATION_TABLE = str.maketrans("", "", string.punctuation)


def normalize_question(question: str) -> str:
    """
    Normaliza pergunta para cache key.

    Regras (mesmas do Go NormalizeQuestion):
      1. Trim whitespace
      2. Lowercase
      3. Collapse multiple spaces
      4. Remove punctuation
    """
    # Trim
    normalized = question.strip()
    # Lowercase
    normalized = normalized.lower()
    # Collapse multiple spaces
    normalized = re.sub(r"\s+", " ", normalized)
    # Remove punctuation
    normalized = normalized.translate(_PUNCTUATION_TABLE)
    # Final trim apos remocao de pontuacao
    return normalized.strip()


def build_cache_key(project_id: str, question: str, version: int = 0) -> str:
    """
    Constroi chave de cache: chat:{project_id}:{question_hash}:{version}

    question_hash = SHA256(normalized_question)[:16]
    """
    normalized = normalize_question(question)
    question_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return f"chat:{project_id}:{question_hash}:{version}"


# ---------------------------------------------------------------------------
# Cache semantico em memoria com TTL
# ---------------------------------------------------------------------------


class InMemoryCache:
    """Cache em memoria com TTL por entrada."""

    def __init__(self, default_ttl_seconds: float = 300.0):
        self._store: dict[str, tuple[Any, float]] = {}  # key -> (value, expiry_ts)
        self._default_ttl = default_ttl_seconds
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Any | None:
        """Retorna valor se existe e nao expirou."""
        entry = self._store.get(key)
        if entry is None:
            self.misses += 1
            return None
        value, expiry_ts = entry
        if time.monotonic() > expiry_ts:
            # Entrada expirada, remover
            del self._store[key]
            self.misses += 1
            return None
        self.hits += 1
        return value

    def set(self, key: str, value: Any, ttl_seconds: float | None = None) -> None:
        """Armazena valor com TTL."""
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        expiry_ts = time.monotonic() + ttl
        self._store[key] = (value, expiry_ts)

    def clear(self) -> None:
        """Limpa todo o cache."""
        self._store.clear()
        self.hits = 0
        self.misses = 0

    @property
    def hit_ratio(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    @property
    def size(self) -> int:
        # Contar apenas entradas nao expiradas
        now = time.monotonic()
        return sum(1 for _, (_, exp) in self._store.items() if now <= exp)


# ---------------------------------------------------------------------------
# FastAPI mock gateway
# ---------------------------------------------------------------------------


def create_app(
    agent_url: str = "http://localhost:9000",
    cache_enabled: bool = True,
    cache_ttl_seconds: float = 300.0,
) -> "FastAPI":
    """Cria aplicacao FastAPI mock gateway com cache configuravel."""
    try:
        from fastapi import FastAPI, HTTPException
        from fastapi.responses import PlainTextResponse
    except ImportError:
        logger.error("FastAPI nao instalado. Instale: pip install fastapi uvicorn")
        raise SystemExit(1)

    try:
        import httpx
    except ImportError:
        logger.error("httpx nao instalado. Instale: pip install httpx")
        raise SystemExit(1)

    app = FastAPI(title="Mock Go Gateway", version="1.0.0")

    # Cache e contadores
    cache = InMemoryCache(default_ttl_seconds=cache_ttl_seconds)
    request_count = 0
    cache_hits = 0
    cache_misses = 0

    # Cliente HTTP compartilhado para proxy
    http_client = httpx.AsyncClient(timeout=30.0)

    # -----------------------------------------------------------------------
    # Endpoints
    # -----------------------------------------------------------------------

    @app.post("/api/v1/chat", response_model=ChatResponse)
    async def chat(req: ChatRequest) -> ChatResponse:
        """
        Endpoint de chat que simula o gateway Go.

        Se cache_enabled=True:
          - Normaliza pergunta, calcula hash, verifica cache
          - HIT: retorna resposta cached (~5ms latencia artificial)
          - MISS: encaminha ao agente Python, armazena no cache

        Se cache_enabled=False:
          - Encaminha diretamente ao agente Python (baseline)
        """
        nonlocal request_count, cache_hits, cache_misses
        request_count += 1

        cache_key = build_cache_key(req.project_id, req.message)
        question_hash = cache_key.split(":")[2]

        if cache_enabled:
            # Tentar cache
            cached = cache.get(cache_key)
            if cached is not None:
                # Cache HIT
                cache_hits += 1
                # Simular latencia de leitura Redis (~5ms)
                await asyncio.sleep(0.005)

                logger.info(
                    "CHAT #%d: HIT project_id=%s hash=%s cache_version=0",
                    request_count,
                    req.project_id,
                    question_hash,
                )

                # Reconstruir resposta do cache
                return ChatResponse(
                    answer=cached["answer"],
                    sources=[Source(**src) for src in cached["sources"]],
                    session_id=req.session_id,
                )

            # Cache MISS - encaminhar ao agente Python
            cache_misses += 1
            logger.info(
                "CHAT #%d: MISS project_id=%s hash=%s cache_version=0",
                request_count,
                req.project_id,
                question_hash,
            )
        else:
            # Cache desabilitado - baseline
            logger.info(
                "CHAT #%d: NOCACHE project_id=%s hash=%s",
                request_count,
                req.project_id,
                question_hash,
            )

        # Encaminhar ao agente Python
        try:
            agent_payload = {
                "project_id": req.project_id,
                "session_id": req.session_id,
                "message": req.message,
            }
            if req.filters is not None:
                agent_payload["filters"] = req.filters

            start = time.perf_counter()
            resp = await http_client.post(
                f"{agent_url.rstrip('/')}/chat",
                json=agent_payload,
            )
            elapsed = time.perf_counter() - start

            if resp.status_code != 200:
                raise HTTPException(
                    status_code=resp.status_code,
                    detail=f"Agent error: {resp.text[:200]}",
                )

            agent_data = resp.json()

            # Se cache habilitado, armazenar resposta
            if cache_enabled:
                cache.set(cache_key, agent_data)

            return ChatResponse(
                answer=agent_data["answer"],
                sources=[Source(**src) for src in agent_data["sources"]],
                session_id=agent_data.get("session_id", req.session_id),
            )

        except httpx.ConnectError:
            raise HTTPException(
                status_code=502,
                detail=f"Cannot connect to Python agent at {agent_url}",
            )
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=504,
                detail="Python agent timeout",
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Health check do mock gateway."""
        return {
            "status": "ok",
            "service": "mock-go-gateway",
            "cache_enabled": str(cache_enabled).lower(),
            "agent_url": agent_url,
        }

    @app.get("/metrics")
    async def metrics() -> PlainTextResponse:
        """Metricas em formato Prometheus text."""
        lines = [
            "# HELP gateway_requests_total Total de requisicoes ao gateway",
            "# TYPE gateway_requests_total counter",
            f"gateway_requests_total {request_count}",
            "",
            "# HELP gateway_cache_hits_total Total de cache hits",
            "# TYPE gateway_cache_hits_total counter",
            f"gateway_cache_hits_total {cache_hits}",
            "",
            "# HELP gateway_cache_misses_total Total de cache misses",
            "# TYPE gateway_cache_misses_total counter",
            f"gateway_cache_misses_total {cache_misses}",
            "",
            "# HELP gateway_cache_hit_ratio Ratio de cache hits (0-1)",
            "# TYPE gateway_cache_hit_ratio gauge",
            f"gateway_cache_hit_ratio {cache.hit_ratio:.4f}",
            "",
            "# HELP gateway_cache_size Entradas ativas no cache",
            "# TYPE gateway_cache_size gauge",
            f"gateway_cache_size {cache.size}",
            "",
        ]
        return PlainTextResponse(content="\n".join(lines))

    @app.get("/cache/stats")
    async def cache_stats() -> dict[str, Any]:
        """Retorna estatisticas do cache em JSON."""
        return {
            "enabled": cache_enabled,
            "hits": cache_hits,
            "misses": cache_misses,
            "hit_ratio": round(cache.hit_ratio, 4),
            "size": cache.size,
            "total_requests": request_count,
        }

    @app.on_event("shutdown")
    async def shutdown() -> None:
        """Fechar cliente HTTP ao desligar."""
        await http_client.aclose()

    return app


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mock do gateway Go com cache semantico para benchmark",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  # Gateway com cache habilitado (padrao)
  python gateway_mock_with_cache.py --port 8080

  # Gateway com cache desabilitado (baseline)
  python gateway_mock_with_cache.py --port 8080 --cache-enabled false

  # Usando variavel de ambiente
  CACHE_ENABLED=false python gateway_mock_with_cache.py --port 8080

  # Apontando para agente em porta customizada
  python gateway_mock_with_cache.py --port 8080 --agent-url http://localhost:9001
""",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Porta do mock gateway (default: 8080)",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host do mock gateway (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--agent-url",
        default="http://localhost:9000",
        help="URL do agente Python (default: http://localhost:9000)",
    )
    parser.add_argument(
        "--cache-enabled",
        default=None,
        choices=["true", "false"],
        help="Habilitar cache (default: env CACHE_ENABLED ou true)",
    )
    parser.add_argument(
        "--cache-ttl",
        type=float,
        default=300.0,
        help="TTL do cache em segundos (default: 300)",
    )

    args = parser.parse_args()

    # Determinar se cache esta habilitado
    # Prioridade: flag CLI > env var > default (true)
    if args.cache_enabled is not None:
        cache_enabled = args.cache_enabled == "true"
    else:
        env_val = os.environ.get("CACHE_ENABLED", "true").lower()
        cache_enabled = env_val == "true"

    logger.info(
        "Iniciando mock gateway na porta %d, agent_url=%s, cache_enabled=%s, cache_ttl=%.0fs",
        args.port,
        args.agent_url,
        cache_enabled,
        args.cache_ttl,
    )

    app = create_app(
        agent_url=args.agent_url,
        cache_enabled=cache_enabled,
        cache_ttl_seconds=args.cache_ttl,
    )

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
        raise SystemExit(1)


if __name__ == "__main__":
    main()
