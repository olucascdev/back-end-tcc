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
- `MINIO_*` - Object storage for document artifacts
- `CHUNK_SIZE` / `CHUNK_OVERLAP` - Text splitting parameters
