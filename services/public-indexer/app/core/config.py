"""
Configuracoes do servico public-indexer.

Carrega variaveis de ambiente com valores default para desenvolvimento.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configuracoes globais do public-indexer."""

    APP_NAME: str = "public-indexer"
    DEBUG: bool = True
    INDEXER_HOST: str = "0.0.0.0"
    INDEXER_PORT: int = 8001

    # PostgreSQL (NeonDB / pgvector)
    DB_URL: str = "postgresql://tcc_user:tcc_pass@localhost:5432/tcc_db"

    # MongoDB (catalogo publico de livros)
    MONGO_URL: str = "mongodb://tcc_mongo_user:tcc_mongo_pass@localhost:27017"
    MONGO_DB: str = "tcc_catalog"

    # MinIO (armazenamento de artefatos)
    MINIO_ENDPOINT: str = "localhost:9002"
    MINIO_ACCESS_KEY: str = "tcc_minio_admin"
    MINIO_SECRET_KEY: str = "tcc_minio_pass"
    MINIO_USE_SSL: bool = False
    MINIO_BUCKET: str = "tcc-public-index"

    # Redis (cache semantico e fila)
    REDIS_URL: str = "redis://localhost:6379/0"

    # Fontes externas
    GOOGLE_BOOKS_API_KEY: str = ""
    OPEN_LIBRARY_BASE_URL: str = "https://openlibrary.org"
    PROJECT_GUTENBERG_BASE_URL: str = "https://www.gutenberg.org"

    # Fontes cientificas (OpenAlex, arXiv, Crossref)
    OPENALEX_ENABLED: bool = True
    OPENALEX_BASE_URL: str = "https://api.openalex.org"
    ARXIV_ENABLED: bool = True
    ARXIV_BASE_URL: str = "http://export.arxiv.org"
    CROSSREF_ENABLED: bool = True
    CROSSREF_BASE_URL: str = "https://api.crossref.org"

    # OpenAI (embeddings)
    OPENAI_API_KEY: str = ""
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-ada-002"

    # Indexacao
    BATCH_SIZE: int = 100
    SYNC_INTERVAL_MINUTES: int = 60
    MAX_RETRIES: int = 3

    # Artefatos
    ARTIFACT_FORMAT_PRIORITY: str = "txt,epub,pdf"
    DOWNLOAD_TIMEOUT: float = 30.0

    # Seguranca — chave para endpoints administrativos
    ADMIN_API_KEY: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}
