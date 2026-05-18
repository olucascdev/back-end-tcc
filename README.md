# TCC Backend — Sistema de Processamento de Documentos com IA e RAG

Backend completo para o projeto de TCC, oferecendo processamento inteligente de documentos e chat com RAG (Retrieval-Augmented Generation). O sistema permite fazer upload de PDFs, extrair e indexar seu conteúdo, e conversar com os documentos usando LLMs com respostas fundamentadas em citações reais.

## Arquitetura

```
┌──────────┐     HTTP      ┌──────────────┐     HTTP      ┌──────────────────┐
│  Usuário │ ────────────► │  Go Gateway   │ ────────────► │  Python Agent     │
│ (Frontend│                │  (Porta 8080) │                │  (Porta 8000)     │
│  / BFF)  │ ◄──────────── │               │ ◄──────────── │                   │
└──────────┘               │  • Roteamento │                │  • Processamento  │
                           │  • Rate Limit │                │    de documentos  │
                           │  • Cache      │                │  • Chat RAG       │
                           │    Semântico  │                │  • Sumarização    │
                           │  • Circuit    │                │  • Comparação     │
                           │    Breaker    │                │  • Fontes públicas│
                           └──────┬───────┘                └────────┬──────────┘
                                  │                                 │
                    ┌─────────────┼─────────────┐         ┌─────────┼──────────┐
                    ▼             ▼             ▼         ▼         ▼          ▼
              ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐ ┌──────┐ ┌────────┐
              │  Redis   │ │PostgreSQL│ │  MinIO   │ │Postgres│ │MinIO │ │OpenAlex│
              │  (Cache  │ │(pgvector │ │(Storage  │ │(Sessões│ │(Docs │ │/Unpay- │
              │semântico)│ │+ sessões)│ │ de PDFs) │ │+ embed)│ │púb.) │ │  wall  │
              └──────────┘ └──────────┘ └──────────┘ └────────┘ └──────┘ └────────┘

  ┌─────────────────────────────────────────────────────────────────────────┐
  │  Public Indexer (DEPRECATED / STUB)                                     │
  │  Era responsável por indexação em massa de livros públicos.             │
  │  Substituído por recuperação sob demanda no Python Agent.               │
  │  → MongoDB (catálogo público)                                           │
  └─────────────────────────────────────────────────────────────────────────┘
```

## O que cada serviço faz

### Go Gateway (`services/go-gateway`)
Ponto de entrada de todas as requisições da API. Recebe chamadas HTTP do frontend/BFF e encaminha para o Python Agent. Além do roteamento, protege o sistema com rate limiting (algoritmo token bucket), armazena respostas de chat similares no Redis (cache semântico) para evitar chamadas repetidas ao LLM, e implementa circuit breaker para parar de chamar o Python Agent quando ele falha repetidamente, retornando erros de forma graciosa.

### Python Agent (`services/python-agent`)
O "cérebro" do sistema. Processa documentos PDF (extraindo texto, dividindo em chunks, gerando embeddings e armazenando no PostgreSQL com pgvector), responde perguntas usando RAG com citações de fontes, sumariza documentos em seções estruturadas, compara múltiplos documentos e mantém histórico de conversas. Suporta também recuperação sob demanda de fontes públicas (OpenAlex, Unpaywall, Google Books) quando ativado o modo `project_plus_public`.

### Public Indexer (`services/public-indexer`) — DEPRECATED
Serviço originalmente projetado para indexação em massa de catálogos públicos de livros. Foi substituído pela recuperação sob demanda no Python Agent, que é mais simples e eficiente para o escopo de um TCC. Mantido apenas com endpoint de health check; endpoints administrativos retornam 503 (serviço descontinuado).

## Pré-requisitos

| Ferramenta | Versão mínima | Para quê |
|---|---|---|
| Docker | 24.0+ | Executar infraestrutura (PostgreSQL, Redis, MongoDB, MinIO) |
| Docker Compose | 2.20+ | Orquestração dos containers |
| Go | 1.22+ | Desenvolvimento do Go Gateway |
| Python | 3.12+ | Desenvolvimento do Python Agent e Public Indexer |

## Passo a passo para configurar

### 1. Clonar o repositório

```bash
git clone <url-do-repositorio>
cd back-end-tcc
```

### 2. Configurar variáveis de ambiente

```bash
cp .env.example .env
# Edite o .env com suas chaves de API e credenciais reais
```

### 3. Iniciar a infraestrutura

```bash
docker compose up -d
```

Isso inicia PostgreSQL, Redis, MongoDB e MinIO. Verifique o status:

```bash
docker compose ps
```

### 4. Configurar o Python Agent

```bash
cd services/python-agent
cp .env.example .env
# Edite .env com sua chave de API (OpenAI, Groq, etc.)

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Iniciar o servidor
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 5. Configurar o Go Gateway

```bash
cd services/go-gateway
cp .env.example .env

go mod tidy
go build -o gateway ./cmd/server
./gateway
```

### 6. Configurar o Public Indexer (opcional, deprecated)

```bash
cd services/public-indexer
cp .env.example .env

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```

### 7. Testar com curl

```bash
# Health check do Go Gateway
curl http://localhost:8080/api/v1/health

# Health check do Python Agent
curl http://localhost:8000/api/v1/health

# Processar um documento PDF
curl -X POST http://localhost:8080/api/v1/process-document \
  -F "file=@seu_documento.pdf" \
  -F "document_id=doc-001"

# Chat RAG com o documento processado
curl -X POST http://localhost:8080/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Qual o tema principal do documento?",
    "session_id": "sessao-001",
    "document_ids": ["doc-001"]
  }'
```

## Tabela de portas dos serviços

| Serviço | Porta | Acesso |
|---|---|---|
| Go Gateway | 8080 | `http://localhost:8080` |
| Python Agent | 8000 | `http://localhost:8000` |
| Public Indexer | 8001 | `http://localhost:8001` (opcional) |
| PostgreSQL | 5432 | `localhost:5432` |
| Redis | 6380 | `localhost:6380` |
| MongoDB | 27017 | `localhost:27017` |
| MinIO API | 9002 | `localhost:9002` |
| MinIO Console | 9003 | `http://localhost:9003` |

> **Nota:** As portas do Redis (6380), MinIO API (9002) e MinIO Console (9003) são mapeadas no `docker-compose.yml` para evitar conflitos com serviços locais. Dentro da rede Docker, os containers usam as portas padrão internas.

## Variáveis de ambiente

### Globais (`.env` na raiz)

| Variável | Descrição | Padrão |
|---|---|---|
| `POSTGRES_USER` | Usuário do PostgreSQL | `tcc_user` |
| `POSTGRES_PASSWORD` | Senha do PostgreSQL | `tcc_pass` |
| `POSTGRES_DB` | Nome do banco | `tcc_db` |
| `REDIS_PASSWORD` | Senha do Redis | `tcc_redis_pass` |
| `MONGO_USER` | Usuário do MongoDB | `tcc_mongo_user` |
| `MONGO_PASSWORD` | Senha do MongoDB | `tcc_mongo_pass` |
| `MINIO_ROOT_USER` | Usuário admin do MinIO | `tcc_minio_admin` |
| `MINIO_ROOT_PASSWORD` | Senha admin do MinIO | `tcc_minio_pass` |
| `CACHE_TTL` | Tempo de vida do cache semântico | `5m` |
| `CACHE_ENABLED` | Habilitar cache semântico | `true` |
| `RATE_LIMIT_BACKEND` | Backend do rate limit (`memory` ou `redis`) | `memory` |
| `RATE_LIMIT_REQUESTS` | Requisições por janela de rate limit | `10` |
| `RATE_LIMIT_BURST` | Burst permitido além do limite | `20` |

### Go Gateway (`services/go-gateway/.env`)

| Variável | Descrição | Padrão |
|---|---|---|
| `GO_GATEWAY_PORT` | Porta do servidor HTTP | `8080` |
| `PYTHON_AGENT_URL` | URL interna do Python Agent | `http://python-agent:8000/api/v1` |
| `REDIS_URL` | Conexão com Redis para cache | — |
| `DB_URL` | Conexão com PostgreSQL | — |
| `RATE_LIMIT_RPS` | Requisições por segundo | `100` |
| `RATE_LIMIT_BURST` | Burst do rate limit | `20` |
| `CIRCUIT_FAILURE_THRESHOLD` | Falhas antes de abrir o circuito | `5` |
| `CIRCUIT_TIMEOUT` | Tempo antes de tentar novamente | `30s` |
| `CACHE_TTL` | TTL do cache semântico (segundos) | `300` |

### Python Agent (`services/python-agent/.env`)

| Variável | Descrição | Padrão |
|---|---|---|
| `PYTHON_AGENT_PORT` | Porta do servidor HTTP | `8000` |
| `DB_URL` | Conexão com PostgreSQL + pgvector | — |
| `OPENAI_API_KEY` | Chave de API do provedor LLM | — |
| `OPENAI_MODEL` | Nome do modelo | `gpt-4o-mini` |
| `OPENAI_BASE_URL` | URL base para provedores compatíveis (vazio = OpenAI padrão) | — |
| `MINIO_ENDPOINT` | Endpoint do MinIO | `localhost:9002` |
| `MINIO_BUCKET` | Bucket para armazenar documentos | `tcc-documents` |
| `EMBEDDING_MODEL` | Modelo de embeddings | `text-embedding-3-small` |
| `CHUNK_SIZE` | Tamanho dos chunks de texto | `512` |
| `CHUNK_OVERLAP` | Sobreposição entre chunks | `64` |
| `MAX_DOCUMENT_SIZE_MB` | Tamanho máximo de documento | `50` |

## Estrutura do projeto

```
back-end-tcc/
├── docker-compose.yml       # Infraestrutura local (PostgreSQL, Redis, MongoDB, MinIO)
├── .env.example             # Template global de variáveis de ambiente
├── .env                     # Variáveis de ambiente (não versionado)
├── .gitignore
├── README.md                # Este arquivo
├── AGENTS.md                # Instruções para agentes de IA
├── Makefile                 # Comandos utilitários
│
├── services/
│   ├── go-gateway/          # Go/Gin — API Gateway
│   │   ├── cmd/server/      # Ponto de entrada
│   │   ├── internal/        # Código interno (api, application, middleware, etc.)
│   │   └── README.md        # Documentação do serviço
│   │
│   ├── python-agent/        # Python/FastAPI+Agno — Agente de IA
│   │   ├── app/             # Código da aplicação (api, domain, infrastructure)
│   │   ├── tests/           # Testes
│   │   └── README.md        # Documentação do serviço
│   │
│   └── public-indexer/      # Python/FastAPI — Indexador público (DEPRECATED)
│       ├── app/             # Código da aplicação
│       ├── tests/           # Testes
│       └── README.md        # Documentação do serviço
│
├── infra/                   # Scripts e configurações de infraestrutura
├── docs/                    # Documentação técnica (PT-BR)
├── openspec/                # Propostas de mudança OpenSpec
├── scripts/                 # Scripts utilitários (quality-gate, etc.)
├── reports/                 # Relatórios de avaliação e qualidade
└── tools/                   # Ferramentas auxiliares
```

## Documentação dos serviços

Cada serviço possui sua própria documentação detalhada:

- **[Go Gateway](services/go-gateway/README.md)** — Roteamento, rate limiting, cache semântico, circuit breaker
- **[Python Agent](services/python-agent/README.md)** — Processamento de documentos, RAG chat, sumarização, comparação
- **[Public Indexer](services/public-indexer/README.md)** — Serviço deprecated (contexto histórico)

## Documentação técnica adicional

Documentos detalhados sobre decisões técnicas, implementação e testes estão em `docs/`:

- `docs/` — Documentação técnica em PT-BR cobrindo arquitetura, decisões e implementação

## Parar a infraestrutura

```bash
docker compose down

# Para remover também os volumes (apaga todos os dados):
docker compose down -v
```

## Credenciais padrão do MinIO Console

- **URL:** http://localhost:9003
- **Usuário:** `tcc_minio_admin`
- **Senha:** `tcc_minio_pass`
