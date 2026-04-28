"""
Configuracoes do servico Python/FastAPI.

Carrega variaveis de ambiente com valores default para desenvolvimento.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configuracoes globais do agente Python."""

    APP_NAME: str = "python-agent"
    DEBUG: bool = True
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/tcc_db"
    REDIS_URL: str = "redis://localhost:6379/0"
    OPENAI_API_KEY: str = ""
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}
