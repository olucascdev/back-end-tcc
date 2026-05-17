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
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "documents"
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    # Feature flags
    ENABLE_PUBLIC_RETRIEVAL: bool = False
    # RAG / LLM settings
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_BASE_URL: str = ""  # Leave empty for default OpenAI; set for Groq or other compatible providers
    MAX_CONTEXT_TOKENS: int = 4000
    SYSTEM_PROMPT: str = (
        "Voce e um assistente especializado em analisar documentos academicos. "
        "Responda sempre com base no contexto fornecido. "
        "Se a informacao nao estiver no contexto, informe que nao ha dados suficientes. "
        "Cite as fontes utilizadas quando possivel."
    )

    # External source clients
    UNPAYWALL_EMAIL: str = "user@example.com"
    GOOGLE_BOOKS_API_KEY: str | None = None

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}
