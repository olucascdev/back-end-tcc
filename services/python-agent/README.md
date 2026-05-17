# Python Agent

AI agent service built with Python, FastAPI, and Agno. Handles document processing, RAG chat with sources, summarization, and document comparison.

## Responsibilities

- Document ingestion and chunking
- Embedding generation and storage (pgvector)
- RAG chat with cited sources
- Document summarization
- Document comparison
- PDF text extraction

## Setup

```bash
# Copy environment file
cp .env.example .env

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt

# Run locally (requires infrastructure running via docker compose)
uvicorn src.main:app --reload --port 8000
```

## Structure (planned)

```
python-agent/
├── src/
│   ├── main.py
│   ├── api/           # FastAPI routers
│   ├── core/          # Config, logging
│   ├── services/      # Business logic
│   ├── models/        # Pydantic schemas, DB models
│   └── infrastructure/# DB, MinIO, LLM clients
├── tests/
├── .env.example
└── README.md
```

## Configuration

See `.env.example` for all available options. Key settings:

- `PYTHON_AGENT_PORT` - HTTP server port (default: 8000)
- `DB_URL` - PostgreSQL connection with pgvector
- `OPENAI_API_KEY` - LLM provider API key
- `OPENAI_MODEL` - Model name (e.g. `gpt-4o-mini`, `llama-3.3-70b-versatile`)
- `OPENAI_BASE_URL` - Base URL for OpenAI-compatible providers (empty = default OpenAI)
- `MINIO_*` - Object storage for document artifacts
- `CHUNK_SIZE` / `CHUNK_OVERLAP` - Text splitting parameters

### Using Groq (OpenAI-compatible)

Groq provides an OpenAI-compatible API with lower latency and cost. To use it:

```env
OPENAI_API_KEY=gsk_your_groq_key_here
OPENAI_MODEL=llama-3.3-70b-versatile
OPENAI_BASE_URL=https://api.groq.com/openai/v1
```

Supported Groq models include `llama-3.3-70b-versatile`, `llama-3.1-8b-instant`, `mixtral-8x7b-32768`, and others. Check [Groq's model list](https://console.groq.com/docs/models) for available options.

**Important — Embeddings with Groq:** Groq does **not** support the embeddings endpoint. When `OPENAI_BASE_URL` points to Groq (or any provider without embeddings), the service automatically detects the error and falls back to deterministic mock embeddings. A structured warning is logged on first occurrence. This allows the full RAG pipeline to work for development and testing. For production-grade embeddings, use the default OpenAI API (leave `OPENAI_BASE_URL` empty) or a provider that supports both chat and embeddings.
