# TCC Backend

Backend system for TCC project with AI-powered document processing and RAG chat.

## Architecture

```
services/
├── go-gateway/          # Go/Gin - API gateway, orchestration, rate limiting, cache
├── python-agent/        # Python/FastAPI+Agno - document processing, RAG chat, summarization
└── public-indexer/      # Python - public book catalog indexer (MongoDB + external APIs)
infra/                   # Infrastructure scripts and configs
```

## Stack

| Component        | Technology              |
|------------------|-------------------------|
| Gateway          | Go + Gin                |
| AI Agent         | Python + FastAPI + Agno |
| Public Indexer   | Python + FastAPI        |
| Database         | PostgreSQL 15 + pgvector|
| Cache            | Redis 7                 |
| Catalog DB       | MongoDB 7               |
| Object Storage   | MinIO (S3-compatible)   |

## Quick Start

### Prerequisites

- Docker >= 24.0
- Docker Compose >= 2.20
- Go >= 1.22 (for go-gateway development)
- Python >= 3.12 (for python-agent and public-indexer development)

### Start Infrastructure

```bash
# Copy environment files
cp .env.example .env

# Start all infrastructure services
docker compose up -d

# Check health status
docker compose ps
```

### Service Ports

| Service    | Port  | Access                    |
|------------|-------|---------------------------|
| PostgreSQL | 5432  | localhost:5432            |
| Redis      | 6379  | localhost:6379            |
| MongoDB    | 27017 | localhost:27017           |
| MinIO API  | 9000  | localhost:9000            |
| MinIO UI   | 9001  | http://localhost:9001     |

### MinIO Console

- URL: http://localhost:9001
- Default credentials: `tcc_minio_admin` / `tcc_minio_pass`

### Stop Infrastructure

```bash
docker compose down

# To also remove volumes (deletes all data):
docker compose down -v
```

## Development

Each service has its own README with setup instructions:

- [Go Gateway](services/go-gateway/README.md)
- [Python Agent](services/python-agent/README.md)
- [Public Indexer](services/public-indexer/README.md)

## Environment Variables

Copy `.env.example` to `.env` and adjust values. Never commit real secrets.

## Project Structure

```
back-end-tcc/
├── docker-compose.yml       # Local infrastructure
├── .env.example             # Global environment template
├── .gitignore
├── README.md
├── AGENTS.md                # AI agent instructions
├── services/
│   ├── go-gateway/          # Go API gateway
│   ├── python-agent/        # Python AI agent
│   └── public-indexer/      # Public catalog indexer
├── infra/                   # Infrastructure scripts
├── docs/                    # Technical documentation (PT-BR)
└── openspec/                # OpenSpec change proposals
```
