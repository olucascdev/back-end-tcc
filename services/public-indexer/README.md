# Public Indexer

> **⚠️ Status: DEPRECATED / STUB**
>
> O pipeline de indexação em massa foi substituído por recuperação sob demanda no **Python Agent**. Este serviço é mantido apenas para contexto histórico e pode ser ignorado na maioria dos casos de uso.

## O que era este serviço?

O Public Indexer foi originalmente projetado para indexar em massa catálogos públicos de livros de fontes externas como Open Library, Project Gutenberg e Google Books. O fluxo planejado era:

1. **Buscar metadados** de APIs públicas (OpenAlex, Gutenberg, OpenLibrary, Google Books)
2. **Baixar artefatos** (PDFs, eBooks) e armazenar no MinIO
3. **Gerar embeddings** do conteúdo textual e armazenar no PostgreSQL com pgvector
4. **Manter catálogo** no MongoDB para consulta e deduplicação
5. **Sincronizar periodicamente** em intervalos configuráveis

## O que ele faz agora?

O serviço foi reduzido a um stub mínimo:

| Método | Caminho | Comportamento |
|---|---|---|
| `GET` | `/api/v1/health` | Health check — retorna `200 OK` se o serviço está vivo |
| `GET` | `/api/v1/health/ready` | Readiness check — verifica dependências |
| `POST` | `/api/v1/admin/index/run` | Retorna `503 Service Unavailable` (serviço descontinuado) |
| `GET` | `/api/v1/admin/index/jobs/{job_id}` | Retorna `503 Service Unavailable` (serviço descontinuado) |

**Nenhum job agendado é executado.** O serviço não indexa, não baixa e não processa documentos.

## Por que foi substituído?

Para um projeto de TCC, a indexação prévia de 100+ livros era desnecessária e complexa demais. A abordagem de **recuperação sob demanda** implementada no Python Agent é mais simples e eficiente:

| Critério | Indexação em massa (antigo) | Recuperação sob demanda (novo) |
|---|---|---|
| **Complexidade** | Alta — requer pipeline completo de ingestão | Baixa — busca apenas quando necessário |
| **Armazenamento** | Persiste todos os artefatos no MinIO | Não persiste — processa e descarta |
| **Custo** | Alto — embeddings de milhares de documentos | Baixo — apenas 3-5 papers por query |
| **Atualização** | Requer re-indexação periódica | Sempre usa dados frescos da API |
| **Escopo TCC** | Overkill para demonstração | Adequado e suficiente |

A recuperação sob demanda busca 3-5 artigos relevantes por consulta, extrai o texto e inclui no contexto RAG. Isso é suficiente para demonstrar o conceito sem a complexidade de um pipeline de indexação completo.

## Como executar (se necessário)

Se você precisar rodar este serviço para fins de teste ou desenvolvimento:

```bash
cd services/public-indexer

# Copiar arquivo de ambiente
cp .env.example .env

# Criar ambiente virtual
python -m venv .venv
source .venv/bin/activate  # Linux/macOS

# Instalar dependências
pip install -r requirements.txt

# Iniciar o servidor
uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```

## Estrutura de pastas

```
public-indexer/
├── app/
│   ├── main.py                  # Aplicação FastAPI com lifespan events
│   ├── __init__.py
│   │
│   ├── api/
│   │   └── v1/
│   │       ├── router.py        # Router principal
│   │       └── endpoints/
│   │           ├── health.py    # GET /health, GET /health/ready
│   │           └── admin.py     # Endpoints admin (retornam 503)
│   │
│   ├── core/
│   │   ├── config.py            # Pydantic Settings carregando .env
│   │   └── logging.py           # Logger estruturado JSON com request_id
│   │
│   ├── domain/
│   │   ├── models.py            # Modelos de domínio (IndexerJob, BookMetadata, etc.)
│   │   └── services.py          # Serviços de domínio (BookCatalogService, JobStore)
│   │
│   ├── infrastructure/
│   │   └── clients.py           # Clientes para MongoDB, PostgreSQL, MinIO, Redis
│   │
│   └── application/
│       └── usecases.py          # Casos de uso (RunIndexUseCase, GetJobStatusUseCase)
│
├── tests/
│   ├── test_health.py           # Testes do endpoint de health
│   └── test_admin.py            # Testes dos endpoints admin
│
├── .env.example                 # Template de variáveis de ambiente
├── .env                         # Variáveis locais (não versionado)
├── requirements.txt             # Dependências Python
├── pyproject.toml               # Configuração do projeto
├── Dockerfile                   # Imagem Docker (não utilizada atualmente)
├── Makefile                     # Comandos utilitários
└── README.md                    # Esta documentação
```

## Configuração — variáveis de ambiente

| Variável | Descrição | Padrão |
|---|---|---|
| `INDEXER_PORT` | Porta do servidor HTTP | `8001` |
| `INDEXER_HOST` | Host de binding | `0.0.0.0` |
| `DB_URL` | Conexão com PostgreSQL + pgvector | — |
| `MONGO_URL` | Conexão com MongoDB para catálogo | — |
| `MONGO_DB` | Nome do banco MongoDB | `tcc_catalog` |
| `MINIO_ENDPOINT` | Endpoint do MinIO | `minio:9000` |
| `MINIO_ACCESS_KEY` | Chave de acesso do MinIO | `tcc_minio_admin` |
| `MINIO_SECRET_KEY` | Chave secreta do MinIO | `tcc_minio_pass` |
| `MINIO_USE_SSL` | Usar SSL com MinIO | `false` |
| `MINIO_BUCKET` | Bucket para artefatos públicos | `tcc-public-index` |
| `REDIS_URL` | Conexão com Redis | — |
| `GOOGLE_BOOKS_API_KEY` | Chave da API Google Books (opcional) | — |
| `OPENALEX_ENABLED` | Habilitar fonte OpenAlex | `true` |
| `ARXIV_ENABLED` | Habilitar fonte arXiv | `true` |
| `CROSSREF_ENABLED` | Habilitar fonte Crossref | `true` |
| `BATCH_SIZE` | Registros por batch durante sync | `100` |
| `SYNC_INTERVAL_MINUTES` | Intervalo de re-sync (não utilizado) | `60` |
| `MAX_RETRIES` | Tentativas máximas em caso de falha | `3` |

## Nota importante

**Este serviço é opcional e pode permanecer desligado.** Ele não é necessário para o funcionamento do sistema principal (Go Gateway + Python Agent). A funcionalidade de recuperação de fontes públicas foi migrada para o Python Agent e funciona sob demanda, sem necessidade de indexação prévia.

Se você está configurando o projeto pela primeira vez, pode ignorar este serviço completamente.
