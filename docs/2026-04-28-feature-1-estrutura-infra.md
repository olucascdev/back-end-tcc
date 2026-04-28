# Feature 1 - Estrutura de repositorio e infraestrutura local

## Contexto

O projeto TCC Backend exige uma base de infraestrutura local funcional antes de qualquer implementacao de logica de negocio. Sem containers de banco de dados, cache, armazenamento de objetos e catalogo rodando localmente, nao e possivel desenvolver, testar ou validar contratos entre servicos.

Esta feature resolve:
- provisionar stack de infraestrutura com Docker Compose
- definir estrutura de pastas para servicos Go, Python e indexer
- padronizar configuracao de ambiente via `.env.example`
- documentar stack e quick start no README raiz

## Decisoes tecnicas

### Docker Compose como orquestrador local
- Docker Compose escolhido por simplicidade e compatibilidade com fluxo de desenvolvimento local.
- Kubernetes ou Helm descartados para fase local — overhead desnecessario.
- Cada servico de infra roda em container isolado com healthcheck proprio.

### Imagens selecionadas
| Servico       | Imagem                     | Motivo                                                     |
|---------------|----------------------------|------------------------------------------------------------|
| PostgreSQL    | `ankane/pgvector:v0.5.1`   | Extensao pgvector embutida, compativel com fluxo NeonDB    |
| Redis         | `redis:7-alpine`           | Versao estavel, imagem leve, suporte a ACL e persistencia  |
| MongoDB       | `mongo:7`                  | Catalogo publico de livros, driver oficial maduro          |
| MinIO         | `minio/minio:latest`       | Compatibilidade S3, console web incluido                   |

### Padrao de ports
Ports mapeados evitam conflito com servicos ja presentes na maquina de desenvolvimento:

| Servico       | Container port | Host port (default) | Variavel env       |
|---------------|----------------|---------------------|--------------------|
| PostgreSQL    | 5432           | 5432                | `POSTGRES_PORT`    |
| Redis         | 6379           | 6380                | `REDIS_PORT`       |
| MongoDB       | 27017          | 27017               | `MONGO_PORT`       |
| MinIO API     | 9000           | 9002                | `MINIO_API_PORT`   |
| MinIO Console | 9001           | 9003                | `MINIO_CONSOLE_PORT` |

- Redis mapeado para `6380` no host para evitar conflito com Redis local existente.
- MinIO API mapeado para `9002` e Console para `9003` para evitar conflito com servicos locais nas ports padrao `9000`/`9001`.
- Todas as ports sao configuraveis via variaveis de ambiente no `.env`.

### Rede interna
- Network `backend-network` do tipo `bridge` isola servicos de infra do host.
- Comunicacao entre servicos usa DNS interno do Docker (ex: `postgres:5432`, `redis:6379`).
- Ports expostas ao host apenas para desenvolvimento e debug.

### Organizacao de pastas
```
back-end-tcc/
├── docker-compose.yml       # Orquestracao de infra local
├── .env.example             # Template de variaveis de ambiente
├── .gitignore               # Exclui .env, artefatos, vendor
├── README.md                # Documentacao principal e quick start
├── AGENTS.md                # Diretrizes para agentes de IA
├── services/
│   ├── go-gateway/          # Go/Gin - gateway, rate limit, circuit breaker
│   ├── python-agent/        # Python/FastAPI+Agno - RAG, chat, summarize
│   └── public-indexer/      # Python - indexador de catalogo publico
├── infra/                   # Scripts de infra (vazio, reservado)
├── docs/                    # Documentacao tecnica em PT-BR
└── openspec/                # Change proposals e specs
```

Cada servico em `services/` contem:
- `.env.example` proprio com variaveis especificas
- `README.md` com instrucoes de setup e desenvolvimento

### Volumes nomeados
- `postgres-data`, `redis-data`, `mongodb-data`, `minio-data`
- Driver `local` para persistencia entre restarts de container.
- Comando `docker compose down -v` remove volumes e limpa estado.

## Implementacao

### Arquivos criados

#### `docker-compose.yml`
- 4 servicos: `postgres`, `redis`, `mongodb`, `minio`
- Healthcheck em cada servico com interval, timeout, retries e start_period configurados
- Volumes nomeados para persistencia de dados
- Network `backend-network` compartilhada
- Variaveis de ambiente com fallback via `${VAR:-default}`

#### `.env.example` (raiz)
- Credenciais e ports para todos os servicos de infra
- URLs internas para comunicacao entre servicos no Docker network
- Comentario explicito: nao commitar `.env` com secrets reais

#### `README.md` (raiz)
- Tabela de stack tecnologica
- Quick start com prerequisitos e comandos
- Tabela de ports e acesso
- Instrucoes para subir/parar infra
- Links para READMEs de cada servico
- Diagrama de estrutura de pastas

#### READMEs e `.env.example` por servico
- `services/go-gateway/README.md` + `.env.example`
- `services/python-agent/README.md` + `.env.example`
- `services/public-indexer/README.md` + `.env.example`

#### `.gitignore`
- Exclui `.env`, `*.log`, `vendor/`, `__pycache__/`, `.venv/`, artefatos de build

## Testes executados

### `docker compose up -d`
Executado com sucesso. Todos os 4 servicos iniciaram e passaram nos healthchecks:

```
NAME             STATUS
tcc-postgres     healthy
tcc-redis        healthy
tcc-mongodb      healthy
tcc-minio        healthy
```

### Problemas encontrados e correcoes

#### Conflito de porta Redis (6379)
- **Problema**: Redis local ja rodando na porta `6379` do host.
- **Correcao**: Mapeamento alterado para `6380:6379` via variavel `REDIS_PORT=6380` no `.env.example`.

#### Conflito de ports MinIO (9000/9001)
- **Problema**: Ports padrao do MinIO (`9000` para API, `9001` para console) conflitam com servicos locais existentes.
- **Correcao**: Mapeamento alterado para `9002:9000` (API) e `9003:9001` (console) via variaveis `MINIO_API_PORT` e `MINIO_CONSOLE_PORT`.

#### Healthcheck do MongoDB
- **Problema**: Healthcheck inicial usava `mongo` CLI, que nao existe na imagem `mongo:7`.
- **Correcao**: Substituido por `mongosh --eval "db.adminCommand('ping')"`.

#### Healthcheck do MinIO
- **Problema**: Healthcheck com `curl` falhava por dependencia nao disponivel na imagem minima.
- **Correcao**: Substituido por `mc ready local`, comando nativo do MinIO client embutido na imagem.

### Validacao de conectividade
- PostgreSQL: acesso via `psql` na porta `5432` confirmado.
- Redis: `redis-cli -p 6380 ping` retorna `PONG`.
- MongoDB: `mongosh --port 27017` conecta com credenciais de root.
- MinIO: console acessivel em `http://localhost:9003`, API em `localhost:9002`.

## Proximos passos

1. **Feature 2 - Modelagem de dados**: criar schemas de tabelas PostgreSQL (users, projects, documents, conversations, agent_sessions), tabela de embeddings com pgvector, colecao MongoDB para books, e scripts de migracao versionados.
2. Definir contratos internos v1 entre Go-Gateway e Python-Agent.
3. Iniciar scaffolds dos servicos com endpoints de health/readiness.
