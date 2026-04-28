# Plano OpenSpec do Backend (Go/Gin + Python/FastAPI+Agno)

## Contexto
Este documento registra a estruturacao inicial em OpenSpec para o backend real do projeto de assistente academico com RAG. O objetivo foi formalizar as capacidades de arquitetura poliglota e regras de governanca para implementacao orientada a SDD.

## Decisoes tecnicas
- OpenSpec adotado como fluxo oficial para mudancas de feature, capacidade e arquitetura.
- Backend dividido em capacidades:
  - Gateway de IA em Go/Gin.
  - Agente RAG em Python/FastAPI+Agno.
  - Plataforma de dados com NeonDB serverless + pgvector.
  - Indexador de catalogo publico com MongoDB + MinIO/S3.
  - Governanca tecnica do repositorio.
- NeonDB definido como banco principal para dados relacionais e vetoriais.
- MongoDB mantido apenas para catalogo publico.

## Implementacao
Foi criado o change OpenSpec:

- `openspec/changes/add-backend-go-python-rag-neondb/proposal.md`
- `openspec/changes/add-backend-go-python-rag-neondb/design.md`
- `openspec/changes/add-backend-go-python-rag-neondb/tasks.md`
- `openspec/changes/add-backend-go-python-rag-neondb/specs/ai-gateway-go/spec.md`
- `openspec/changes/add-backend-go-python-rag-neondb/specs/rag-agent-python/spec.md`
- `openspec/changes/add-backend-go-python-rag-neondb/specs/data-platform-neondb-pgvector/spec.md`
- `openspec/changes/add-backend-go-python-rag-neondb/specs/public-catalog-indexer/spec.md`
- `openspec/changes/add-backend-go-python-rag-neondb/specs/backend-governance/spec.md`

Tambem foram atualizados arquivos centrais para guiar os agentes:

- `AGENTS.md` (raiz) com diretrizes obrigatorias de backend.
- `openspec/project.md` com contexto real, stack e convencoes do projeto.

## Testes executados
- Validacao estrita do change OpenSpec:
  - `openspec validate add-backend-go-python-rag-neondb --strict`
  - Resultado: valido sem erros.

## Proximos passos
1. Aprovar formalmente o change `add-backend-go-python-rag-neondb`.
2. Iniciar implementacao da Fase 1 (MVP) seguindo `tasks.md` e specs.
3. Gerar novo arquivo em `docs/` a cada feature/plano implementado, mantendo rastreabilidade tecnica.
