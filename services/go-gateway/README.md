# Go Gateway

API gateway built with Go and Gin. Handles request routing, rate limiting, semantic caching, circuit breaking, and PDF processing queue orchestration.

## Responsibilities

- Request routing to Python agent service
- Rate limiting (token bucket / sliding window)
- Semantic cache with Redis
- Circuit breaker for Python agent calls
- PDF processing queue management
- Health check endpoints

## Setup

```bash
# Copy environment file
cp .env.example .env

# Install dependencies
go mod tidy

# Run locally (requires infrastructure running via docker compose)
go run cmd/server/main.go
```

## Structure (planned)

```
go-gateway/
├── cmd/
│   └── server/
│       └── main.go
├── internal/
│   ├── transport/     # HTTP handlers, middleware
│   ├── application/   # Use cases, orchestration
│   ├── domain/        # Entities, interfaces
│   └── infrastructure/# DB, Redis, MinIO clients
├── pkg/               # Shared utilities
├── .env.example
└── README.md
```

## Configuration

See `.env.example` for all available options. Key settings:

- `GO_GATEWAY_PORT` - HTTP server port (default: 8080)
- `PYTHON_AGENT_URL` - Internal URL for Python agent service
- `REDIS_URL` - Redis connection for caching
- `DB_URL` - PostgreSQL connection
- `RATE_LIMIT_RPS` - Requests per second limit
- `CIRCUIT_BREAKER_THRESHOLD` - Failures before opening circuit
