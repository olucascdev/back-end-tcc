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
uvicorn app.main:app --reload --port 8001
```

## Structure

```
public-indexer/
├── app/
│   ├── main.py              # FastAPI app with lifespan events
│   ├── core/
│   │   ├── config.py        # Pydantic Settings loading .env
│   │   └── logging.py       # Structured JSON logger with request_id
│   ├── api/v1/
│   │   ├── router.py        # API router
│   │   └── endpoints/
│   │       ├── health.py    # GET /health, GET /health/ready
│   │       └── admin.py     # POST /admin/index/run, GET /admin/index/jobs/{job_id}
│   ├── domain/
│   │   ├── models.py        # Domain models (IndexerJob, BookMetadata, EmbeddingMetadata)
│   │   └── services.py      # Domain services (BookCatalogService, JobStore)
│   ├── infrastructure/
│   │   └── clients.py       # Clients for MongoDB, PostgreSQL, MinIO, Redis
│   └── application/
│       └── usecases.py      # Use cases (RunIndexUseCase, GetJobStatusUseCase)
├── tests/
│   ├── test_health.py       # Health endpoint tests
│   └── test_admin.py        # Admin endpoint tests
├── Dockerfile
├── Makefile
├── pyproject.toml
├── requirements.txt
├── .env.example
└── README.md
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/health` | Basic health check (returns 200 if service is alive) |
| GET | `/api/v1/health/ready` | Readiness check (verifies all dependencies) |
| POST | `/api/v1/admin/index/run` | Trigger indexing job (optional body: source_filter, dry_run) |
| GET | `/api/v1/admin/index/jobs/{job_id}` | Get job status (pending/running/completed/failed) |

## Configuration

See `.env.example` for all available options. Key settings:

- `INDEXER_PORT` - HTTP server port (default: 8001)
- `DB_URL` - PostgreSQL connection for embeddings
- `MONGO_URL` - MongoDB connection for book catalog
- `REDIS_URL` - Redis connection for cache and queue
- `MINIO_ENDPOINT` - MinIO/S3 endpoint for artifact storage
- `GOOGLE_BOOKS_API_KEY` - Google Books API key (optional)
- `SYNC_INTERVAL_MINUTES` - How often to re-sync sources
- `BATCH_SIZE` - Records per batch during sync

## Metadata Contract

Embeddings stored in PostgreSQL must include the following JSONB metadata fields:

| Field | Type | Description |
|-------|------|-------------|
| `source_type` | string | Origin type (e.g., `public_library`, `user_upload`) |
| `source_provider` | string | Source provider (e.g., `gutenberg`, `openlibrary`, `google_books`) |
| `source_id` | string | Unique identifier in the original source |
| `artifact_key` | string | MinIO/S3 key of the artifact |
| `checksum` | string | Content hash for integrity verification |
| `chunk_version` | int | Chunk version for reprocessing (default: 1) |

## Deduplication Policy

- **Stable book keys**: `gutenberg_id` → `ol_key` → hash(title+authors)
- **Chunk fingerprint**: `source_id + checksum + chunk_version`
