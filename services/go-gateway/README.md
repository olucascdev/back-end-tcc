# Go Gateway

API Gateway construído com Go e Gin. É o ponto de entrada de todas as requisições da API, recebendo chamadas HTTP do frontend/BFF e encaminhando para os serviços internos.

## O que é o Go Gateway?

O Go Gateway é a porta de entrada do sistema. Toda requisição que vem do frontend ou BFF passa por ele primeiro. Sua função principal é receber as requisições, aplicar proteções (rate limiting, cache), encaminhar para o Python Agent e tratar os retornos — convertendo erros do Python em códigos HTTP adequados para o cliente.

## Responsabilidades detalhadas

### Roteamento de requisições
Recebe requisições em `/api/v1/*` e encaminha para o Python Agent. O gateway atua como proxy reverso, mantendo o Python Agent isolado do mundo externo.

### Rate Limiting
Protege o sistema contra abuso usando o algoritmo **token bucket**. Cada cliente tem um balde de tokens que se enche a uma taxa fixa. Cada requisição consome um token; quando o balde esvazia, requisições adicionais são rejeitadas com `429 Too Many Requests`. Suporta dois backends:
- **`memory`**: Token bucket local (padrão, ideal para desenvolvimento)
- **`redis`**: Rate limiting distribuído via `INCR/EXPIRE` do Redis (ideal para produção com múltiplas instâncias)

### Cache Semântico
Armazena respostas de chat no Redis para evitar chamadas repetidas ao LLM quando perguntas semanticamente similares são feitas. Funciona assim:
1. Gera um embedding da pergunta do usuário
2. Busca no Redis por embeddings similares (dentro de um limiar de similaridade)
3. Se encontrar um cache hit, retorna a resposta armazenada sem chamar o LLM
4. Se não encontrar, encaminha ao Python Agent e armazena a resposta para uso futuro

Isso reduz custos com LLM e melhora a latência para perguntas frequentes.

### Circuit Breaker
Se o Python Agent começar a falhar repetidamente, o circuit breaker "abre" e para de enviar requisições temporariamente, retornando um erro gracioso ao cliente. Isso evita:
- Cascata de falhas quando o Python Agent está sobrecarregado
- Desperdício de recursos tentando chamar um serviço indisponível
- Timeouts longos para o usuário final

O circuito se fecha automaticamente após um tempo configurável (`CIRCUIT_TIMEOUT`), permitindo que o Python Agent se recupere.

### Fila de Processamento de PDF
Gerencia jobs assíncronos de processamento de PDF. Quando um documento é enviado:
1. O gateway aceita o upload e cria um job
2. Encaminha o documento para o Python Agent processar
3. O cliente pode consultar o status do job posteriormente

### Tratamento de erros
Mapeia erros do Python Agent para códigos HTTP apropriados:
- `400` do Python Agent → `400 Bad Request`
- `404` do Python Agent → `404 Not Found`
- `500` do Python Agent → `502 Bad Gateway`
- Timeout → `504 Gateway Timeout`
- Circuit breaker aberto → `503 Service Unavailable`

## Como executar

```bash
cd services/go-gateway

# Copiar arquivo de ambiente
cp .env.example .env

# Instalar dependências
go mod tidy

# Compilar
go build -o gateway ./cmd/server

# Executar
./gateway
```

Ou para desenvolvimento com hot reload:

```bash
go run cmd/server/main.go
```

> **Nota:** A infraestrutura (PostgreSQL, Redis, MinIO) precisa estar rodando via `docker compose up -d` antes de iniciar o gateway.

## Endpoints principais

| Método | Caminho | Descrição |
|---|---|---|
| `GET` | `/api/v1/health` | Health check do gateway |
| `POST` | `/api/v1/chat` | Chat RAG — encaminha para o Python Agent |
| `POST` | `/api/v1/process-document` | Processamento de documento PDF |
| `POST` | `/api/v1/summarize-document` | Sumarização de documento |
| `POST` | `/api/v1/compare-documents` | Comparação entre documentos |

## Configuração — variáveis de ambiente

| Variável | Descrição | Padrão |
|---|---|---|
| `GO_GATEWAY_PORT` | Porta do servidor HTTP | `8080` |
| `GO_GATEWAY_HOST` | Host de binding | `0.0.0.0` |
| `PYTHON_AGENT_URL` | URL interna do Python Agent | `http://python-agent:8000/api/v1` |
| `REDIS_URL` | Conexão com Redis para cache semântico | — |
| `DB_URL` | Conexão com PostgreSQL | — |
| `MINIO_ENDPOINT` | Endpoint do MinIO | `localhost:9002` |
| `MINIO_ACCESS_KEY` | Chave de acesso do MinIO | `tcc_minio_admin` |
| `MINIO_SECRET_KEY` | Chave secreta do MinIO | `tcc_minio_pass` |
| `MINIO_USE_SSL` | Usar SSL com MinIO | `false` |
| `RATE_LIMIT_RPS` | Requisições por segundo (rate limit) | `100` |
| `RATE_LIMIT_BURST` | Burst permitido além do limite | `20` |
| `CIRCUIT_MAX_REQUESTS` | Requisições máximas simultâneas por circuito | `3` |
| `CIRCUIT_FAILURE_THRESHOLD` | Número de falhas antes de abrir o circuito | `5` |
| `CIRCUIT_TIMEOUT` | Tempo antes de tentar novamente (ex: `30s`) | `30s` |
| `CACHE_TTL` | TTL do cache semântico em segundos | `300` |

## Arquitetura — estrutura de pastas

```
go-gateway/
├── cmd/
│   └── server/
│       └── main.go              # Ponto de entrada — inicializa servidor, config e dependências
│
├── internal/
│   ├── api/                     # Handlers HTTP e roteamento Gin
│   ├── app/                     # Inicialização da aplicação (wire de dependências)
│   ├── application/             # Casos de uso e orquestração de serviços
│   ├── client/                  # Clientes HTTP para serviços externos (Python Agent)
│   ├── config/                  # Carregamento de configuração (.env)
│   ├── contracts/               # Interfaces e contratos entre camadas
│   ├── infrastructure/          # Implementações de infraestrutura (Redis, PostgreSQL, MinIO)
│   ├── logger/                  # Configuração de logging estruturado
│   └── middleware/              # Middlewares Gin (rate limit, circuit breaker, logging)
│
├── pkg/                         # Utilitários compartilhados (se houver)
├── .env.example                 # Template de variáveis de ambiente
├── .env                         # Variáveis de ambiente locais (não versionado)
├── go.mod / go.sum              # Dependências Go
└── README.md                    # Esta documentação
```

### Camadas internas

O gateway segue uma arquitetura em camadas:

- **`api/`** — Camada de transporte: handlers HTTP, parsing de requests/responses, roteamento
- **`application/`** — Casos de uso: lógica de negócio como "processar documento", "encaminhar chat"
- **`domain/`** — Entidades e interfaces: modelos de domínio e contratos abstratos
- **`infrastructure/`** — Implementações concretas: clientes Redis, PostgreSQL, MinIO
- **`middleware/`** — Cross-cutting concerns: rate limiting, circuit breaker, logging
- **`client/`** — Clientes HTTP: comunicação com o Python Agent
