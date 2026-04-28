# Public Indexer

Service for indexing public book catalogs from external sources (Open Library, Project Gutenberg, Google Books) into MongoDB and PostgreSQL.

## Responsibilities

- Fetch book metadata from public APIs
- Sync catalog to MongoDB
- Generate and store embeddings in PostgreSQL (pgvector)
- Scheduled periodic synchronization
- Deduplication and conflict resolution

## Setup

```bash
# Copy environment file
cp .env.example .env

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS

# Install dependencies
pip install -r requirements.txt

# Run locally (requires infrastructure running via docker compose)
uvicorn src.main:app --reload --port 8001
```

## Structure (planned)

```
public-indexer/
├── src/
│   ├── main.py
│   ├── api/           # FastAPI routers (admin endpoints)
│   ├── core/          # Config, logging
│   ├── services/      # Indexing logic, API clients
│   ├── models/        # Pydantic schemas, DB models
│   └── infrastructure/# DB, MinIO, external API clients
├── tests/
├── .env.example
└── README.md
```

## Configuration

See `.env.example` for all available options. Key settings:

- `INDEXER_PORT` - HTTP server port (default: 8001)
- `DB_URL` - PostgreSQL connection for embeddings
- `MONGO_URL` - MongoDB connection for book catalog
- `GOOGLE_BOOKS_API_KEY` - Google Books API key (optional)
- `SYNC_INTERVAL_MINUTES` - How often to re-sync sources
- `BATCH_SIZE` - Records per batch during sync
