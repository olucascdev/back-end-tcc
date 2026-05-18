# Python Agent

Agente de IA construído com Python, FastAPI e Agno. É o "cérebro" do sistema — processa documentos, responde perguntas usando RAG (Retrieval-Augmented Generation), sumariza textos e compara documentos.

## O que é o Python Agent?

O Python Agent é o serviço responsável por toda a inteligência do sistema. Ele recebe documentos PDF, extrai o texto, divide em pedaços menores (chunks), gera vetores de representação (embeddings) e armazena no PostgreSQL com extensão pgvector. Quando o usuário faz uma pergunta, o agente busca os trechos mais relevantes dos documentos e usa um LLM para gerar uma resposta fundamentada, com citações das fontes originais.

## Responsabilidades detalhadas

### Processamento de documentos
Quando um PDF é enviado:
1. **Extração de texto**: Lê o PDF e extrai o conteúdo textual
2. **Chunking**: Divide o texto em pedaços de tamanho configurável (padrão: 512 caracteres com 64 de sobreposição)
3. **Embeddings**: Gera vetores numéricos para cada chunk usando um modelo de embedding (ex: `text-embedding-3-small`)
4. **Armazenamento**: Salva os embeddings no PostgreSQL com pgvector e o documento original no MinIO
5. **Metadados**: Associa cada chunk a metadados como `document_id`, `chunk_index`, `source_type`

### Chat RAG com fontes
Quando o usuário faz uma pergunta:
1. **Busca semântica**: Converte a pergunta em embedding e busca os chunks mais similares no pgvector
2. **Construção de contexto**: Monta um prompt com os chunks relevantes encontrados
3. **Geração de resposta**: Envia o prompt ao LLM para gerar uma resposta fundamentada
4. **Citações**: Inclui referências às fontes originais na resposta
5. **Memória de sessão**: Persiste o histórico da conversa no PostgreSQL para manter contexto entre mensagens

### Recuperação de fontes públicas (NOVO)
Quando `retrieval_mode="project_plus_public"`, o agente busca artigos acadêmicos sob demanda de fontes externas:
1. **OpenAlex API**: Busca trabalhos acadêmicos relevantes por palavras-chave
2. **Unpaywall**: Encontra versões abertas (open access) dos artigos
3. **Google Books**: Complementa com livros disponíveis publicamente
4. **Download e extração**: Baixa os PDFs, extrai texto e inclui no contexto RAG
5. **Sem armazenamento persistente**: Os artefatos públicos são processados sob demanda e não persistidos

**Cadeia de fallback para fontes públicas:**
```
OpenAlex → Unpaywall → Google Books
```
Se uma fonte falhar, a próxima é tentada automaticamente.

### Sumarização
Gera resumos estruturados de documentos em seções como:
- Tema principal
- Pontos-chave
- Conclusões
- Tópicos relevantes

### Comparação de documentos
Compara múltiplos documentos lado a lado, identificando:
- Semelhanças temáticas
- Diferenças de abordagem
- Pontos de convergência e divergência

### Memória de sessão
Persiste o histórico de conversas no PostgreSQL, permitindo:
- Continuar conversas anteriores
- Manter contexto entre múltiplas mensagens
- Recuperar sessões por `session_id`

## Como executar

```bash
cd services/python-agent

# Copiar arquivo de ambiente
cp .env.example .env

# Criar ambiente virtual
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# Instalar dependências
pip install -r requirements.txt

# Iniciar o servidor
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

> **Nota:** A infraestrutura (PostgreSQL, Redis, MinIO) precisa estar rodando via `docker compose up -d` antes de iniciar o agente.

## Endpoints principais

| Método | Caminho | Descrição |
|---|---|---|
| `GET` | `/api/v1/health` | Health check do serviço |
| `POST` | `/api/v1/chat` | Chat RAG com fontes citadas |
| `POST` | `/api/v1/process-document` | Ingestão e processamento de PDF |
| `POST` | `/api/v1/summarize-document` | Sumarização de documento |
| `POST` | `/api/v1/compare-documents` | Comparação entre documentos |

### Exemplo: Chat RAG

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Qual o tema principal do documento?",
    "session_id": "sessao-001",
    "document_ids": ["doc-001"],
    "retrieval_mode": "project_only"
  }'
```

### Exemplo: Processar documento

```bash
curl -X POST http://localhost:8000/api/v1/process-document \
  -F "file=@meu_documento.pdf" \
  -F "document_id=doc-001"
```

## Configuração — variáveis de ambiente

| Variável | Descrição | Padrão |
|---|---|---|
| `PYTHON_AGENT_PORT` | Porta do servidor HTTP | `8000` |
| `PYTHON_AGENT_HOST` | Host de binding | `0.0.0.0` |
| `DB_URL` | Conexão com PostgreSQL + pgvector | — |
| `OPENAI_API_KEY` | Chave de API do provedor LLM | — |
| `OPENAI_MODEL` | Nome do modelo LLM | `gpt-4o-mini` |
| `OPENAI_BASE_URL` | URL base para provedores compatíveis (vazio = OpenAI padrão) | — |
| `MINIO_ENDPOINT` | Endpoint do MinIO | `localhost:9002` |
| `MINIO_ACCESS_KEY` | Chave de acesso do MinIO | `tcc_minio_admin` |
| `MINIO_SECRET_KEY` | Chave secreta do MinIO | `tcc_minio_pass` |
| `MINIO_USE_SSL` | Usar SSL com MinIO | `false` |
| `MINIO_BUCKET` | Bucket para armazenar documentos | `tcc-documents` |
| `EMBEDDING_MODEL` | Modelo de embeddings | `text-embedding-3-small` |
| `EMBEDDING_DIMENSION` | Dimensão dos vetores de embedding | `1536` |
| `CHUNK_SIZE` | Tamanho dos chunks de texto | `512` |
| `CHUNK_OVERLAP` | Sobreposição entre chunks | `64` |
| `MAX_DOCUMENT_SIZE_MB` | Tamanho máximo de documento em MB | `50` |

### Usando Groq (compatível com OpenAI)

O Groq oferece uma API compatível com OpenAI com menor latência e custo. Para usar:

```env
OPENAI_API_KEY=gsk_sua_chave_groq_aqui
OPENAI_MODEL=llama-3.3-70b-versatile
OPENAI_BASE_URL=https://api.groq.com/openai/v1
```

Modelos Groq suportados incluem `llama-3.3-70b-versatile`, `llama-3.1-8b-instant`, `mixtral-8x7b-32768` e outros. Consulte a [lista de modelos do Groq](https://console.groq.com/docs/models) para opções disponíveis.

> **Importante — Embeddings com Groq:** O Groq **não** suporta o endpoint de embeddings. Quando `OPENAI_BASE_URL` aponta para o Groq (ou qualquer provedor sem embeddings), o serviço detecta o erro automaticamente e faz fallback para embeddings mock determinísticos. Um aviso estruturado é registrado no log na primeira ocorrência. Isso permite que o pipeline RAG completo funcione para desenvolvimento e testes. Para embeddings em produção, use a API OpenAI padrão (deixe `OPENAI_BASE_URL` vazio) ou um provedor que suporte tanto chat quanto embeddings.

## Arquitetura — estrutura de pastas

```
python-agent/
├── app/
│   ├── main.py                  # Aplicação FastAPI com lifespan events
│   ├── __init__.py
│   │
│   ├── api/                     # Roteadores FastAPI (camada de transporte)
│   │   ├── v1/                  # Versão 1 da API
│   │   │   ├── router.py        # Router principal
│   │   │   └── endpoints/       # Handlers de cada endpoint
│   │   │       ├── chat.py      # POST /chat
│   │   │       ├── documents.py # POST /process-document
│   │   │       ├── summarize.py # POST /summarize-document
│   │   │       ├── compare.py   # POST /compare-documents
│   │   │       └── health.py    # GET /health
│   │
│   ├── core/                    # Configuração e utilitários centrais
│   │   ├── config.py            # Pydantic Settings carregando .env
│   │   └── logging.py           # Logger estruturado
│   │
│   ├── domain/                  # Modelos de domínio e lógica de negócio
│   │   ├── models.py            # Entidades de domínio
│   │   └── services.py          # Serviços de domínio (RAG, chunking, etc.)
│   │
│   ├── infrastructure/          # Implementações de infraestrutura
│   │   ├── database.py          # Conexão com PostgreSQL + pgvector
│   │   ├── minio_client.py      # Cliente MinIO para armazenamento
│   │   ├── llm_client.py        # Cliente LLM (OpenAI/Groq)
│   │   └── embedding.py         # Geração de embeddings
│   │
│   └── schemas/                 # Modelos Pydantic para request/response
│
├── tests/                       # Testes unitários e de integração
├── scripts/                     # Scripts utilitários
├── docs/                        # Documentação do serviço
├── .env.example                 # Template de variáveis de ambiente
├── .env                         # Variáveis locais (não versionado)
├── requirements.txt             # Dependências Python
├── pyproject.toml               # Configuração do projeto
└── README.md                    # Esta documentação
```

### Camadas internas

O agente segue uma arquitetura em camadas inspirada em Clean Architecture:

- **`api/`** — Camada de transporte: roteadores FastAPI, handlers HTTP, validação de requests
- **`domain/`** — Lógica de negócio pura: serviços de RAG, chunking, comparação, sumarização
- **`infrastructure/`** — Implementações concretas: clientes de banco de dados, MinIO, LLM, embeddings
- **`core/`** — Configuração transversal: settings, logging, constantes
- **`schemas/`** — Contratos de dados: modelos Pydantic para entrada e saída da API

## Fontes públicas — cadeia de fallback

Quando o modo de recuperação `project_plus_public` está ativado, o agente busca artigos acadêmicos de fontes externas usando esta cadeia de fallback:

```
┌──────────┐    falha     ┌───────────┐    falha     ┌──────────────┐
│  OpenAlex │ ──────────► │ Unpaywall │ ──────────► │ Google Books  │
│  (primary)│             │  (OA PDF) │             │  (fallback)   │
└──────────┘              └───────────┘              └──────────────┘
```

1. **OpenAlex**: API aberta de metadados acadêmicos (trabalhos, autores, conceitos). Busca artigos relevantes por palavras-chave e retorna metadados estruturados.
2. **Unpaywall**: Encontra versões open access de artigos acadêmicos via DOI. Fornece links diretos para PDFs gratuitos.
3. **Google Books**: Complementa com livros disponíveis publicamente quando as fontes acadêmicas não retornam resultados suficientes.

Os artigos encontrados são baixados, o texto é extraído e incluído no contexto RAG para a geração da resposta. Os artefatos **não** são persistidos — são processados sob demanda a cada query.
