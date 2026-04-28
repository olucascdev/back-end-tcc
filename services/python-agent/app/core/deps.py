"""
Injecao de dependencia basica.

Fornecedores reutilizaveis via Depends() do FastAPI.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from app.core.config import Settings


def get_settings() -> Settings:
    """Retorna instancia singleton de Settings."""
    return Settings()


async def get_db() -> AsyncGenerator[Any, None]:
    """Placeholder para conexao com banco de dados.

    Por enquanto yield None; sera substituido por engine async real.
    """
    yield None
