# Fase 0 - Fundacao tecnica do backend

## Contexto
Fase 0 prepara base estrutural para implementacao do backend poliglota do assistente academico com RAG. Escopo inclui apenas backend real: Go/Gin, Python/FastAPI+Agno, NeonDB+pgvector, Redis, MongoDB e MinIO/S3.

Objetivo central da fase:
- travar contratos internos v1
- travar modelo de dados inicial
- subir scaffolds dos servicos
- habilitar observabilidade, seguranca baseline e quality gates

Fora de escopo desta fase:
- features RAG completas em producao
- indexador publico completo
- otimizacoes avancadas de cache semantico

## Decisoes tecnicas
- Arquitetura por servico:
  - Go/Gin: gateway de IA, resiliencia e orquestracao.
  - Python/FastAPI+Agno: endpoints e fundacao de pipeline RAG.
  - NeonDB serverless + pgvector: dados principais e embeddings.
  - MongoDB: catalogo publico.
  - Redis: cache semantico futuro e estado de rate limiting.
- Contratos internos versionados (`v1`) como fonte de verdade entre servicos.
- Arquitetura em camadas por servico: `transport`, `application`, `domain`, `infrastructure`.
- Regras de repositorio mantidas:
  - comentarios em codigo PT-BR
  - nomenclatura tecnica em ingles
  - commits em ingles com Conventional Commits
  - docs em PT-BR para cada feature/plano

## Implementacao

### 1) Governanca SDD e estrutura de repositorio
- Criar/validar estrutura:
  - `services/go-gateway/`
  - `services/python-agent/`
  - `services/public-indexer/`
  - `infra/`
  - `docs/`
- Garantir OpenSpec ativo:
  - `proposal.md`, `design.md`, `tasks.md`, deltas por capability
- Entregavel: baseline de organizacao e trilha SDD operacional.

### 2) Contratos internos v1
- Definir contrato `POST /process-document` (Go -> Python):
  - request: `project_id`, `document_id`, `storage_key`, `source_type`, metadata minima
  - response: status de processamento, contagem chunks, tempos, erro estruturado
- Definir contrato `POST /chat` (Go -> Python):
  - request: `project_id`, `session_id`, `message`, filtros opcionais
  - response: `answer`, `sources[]` com `document`, `page`, `section`
- Definir contrato de webhook (Go -> BFF):
  - status: `pending | processing | ready | error`
  - payload minimo: ids, timestamps, mensagem de erro normalizada
- Definir politica de versionamento:
  - `v1` para baseline
  - breaking change exige nova versao

### 3) Dados e migracoes
- NeonDB relacional:
  - `users`
  - `projects`
  - `documents`
  - `conversations`
  - `agent_sessions`
- NeonDB vetorial (pgvector):
  - tabela de embeddings com metadata (`project_id`, `source_type`, `filename`, `page`)
  - indice vetorial para similaridade
- MongoDB:
  - colecao `books` com `title`, `authors`, `isbn`, `gutenberg_id`, `ol_key`, `formats`, `indexed`, `indexed_at`
- Migracoes:
  - padrao versionado
  - estrategia up/down documentada

### 4) Go/Gin base (gateway)
- Subir servidor HTTP com:
  - `GET /health`
  - `GET /ready`
- Criar cliente HTTP interno para Python com timeout + retry baseline.
- Criar scaffold de:
  - rate limiting
  - circuit breaker
  - fila de jobs PDF (base)
- Entregavel: servico pronto para conectar endpoints reais da Fase 1.

### 5) Python/FastAPI base (agent)
- Subir app FastAPI com:
  - `GET /health`
  - `GET /ready`
  - `GET /version`
- Criar endpoints stub v1:
  - `POST /process-document`
  - `POST /chat`
  - `POST /summarize-document`
  - `POST /compare-documents`
- Criar interfaces internas para chunking, embeddings, retrieval e session store.

### 6) Infra local e configuracao
- Definir `.env.example` por servico.
- Validacao de env obrigatorias no startup.
- Subir stack local de dependencia:
  - Postgres+pgvector (compativel fluxo Neon)
  - Redis
  - MongoDB
  - MinIO/S3
- Definir limites basicos de seguranca:
  - timeout global
  - limite de payload
  - politica de segredo (sem commit de segredo real)

### 7) Observabilidade e quality gates
- Logging estruturado com correlacao:
  - `request_id`, `project_id`, `user_id`, `document_id`
- Metricas base por endpoint:
  - latencia
  - throughput
  - taxa de erro
- CI minimo:
  - lint
  - format check
  - testes unitarios baseline
- Testes obrigatorios da fase:
  - smoke HTTP
  - migracoes
  - contratos internos

### 8) DoD (Definition of Done) da Fase 0
- contratos v1 congelados e versionados
- migracoes executam limpo
- Go e Python sobem com health/readiness
- CI baseline verde
- OpenSpec validado em modo estrito
- documentacao da fase atualizada em `docs/`

## Testes executados
Para aplicacao do plano (documentacao), foram executados testes de consistencia de processo:
- verificacao de aderencia ao OpenSpec existente
- verificacao de aderencia as diretrizes de `AGENTS.md` e `openspec/project.md`

Testes tecnicos de codigo (runtime, migracoes, carga) serao executados durante implementacao da fase.

## Proximos passos
1. Converter este plano em tarefas operacionais de 1-2 dias no `tasks.md` do change ativo.
2. Iniciar implementacao pelos blocos: contratos v1 -> dados/migracoes -> bootstrap Go/Python.
3. Gerar docs incrementais por feature entregue dentro da Fase 0.
