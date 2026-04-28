<!-- OPENSPEC:START -->
# OpenSpec Instructions

These instructions are for AI assistants working in this project.

Always open `@/openspec/AGENTS.md` when the request:
- Mentions planning or proposals (words like proposal, spec, change, plan)
- Introduces new capabilities, breaking changes, architecture shifts, or big performance/security work
- Sounds ambiguous and you need the authoritative spec before coding

Use `@/openspec/AGENTS.md` to learn:
- How to create and apply change proposals
- Spec format and conventions
- Project structure and guidelines

Keep this managed block so 'openspec update' can refresh the instructions.

<!-- OPENSPEC:END -->

# Diretrizes do Repositorio (Backend)

## Escopo
- Este repositorio cobre backend real do projeto (Go/Gin e Python/FastAPI+Agno) e dados.
- Frontend e BFF ficam fora deste escopo de implementacao.

## Regras obrigatorias
- Usar SDD com OpenSpec para mudancas de feature/capacidade/arquitetura.
- Toda feature ou plano implementado deve gerar arquivo em `docs/*.md` em PT-BR explicando:
  - contexto
  - decisoes tecnicas
  - implementacao
  - testes executados
  - proximos passos
- Comentarios de codigo sempre em PT-BR.
- Commits sempre em ingles seguindo Conventional Commits.
- Nomenclatura de codigo sempre em ingles (variaveis, funcoes, classes, identificadores).

## Boas praticas tecnicas
- Aplicar Clean Code e separacao de responsabilidades.
- Preferir arquitetura em camadas por servico (transport/application/domain/infrastructure).
- Evitar acoplamento entre servicos; comunicar por contratos internos versionados.
- Tratar resiliencia no gateway Go (timeout/retry/circuit breaker/rate limit).

## Stack e responsabilidade
- Go/Gin: orquestracao IA, rate limiting, cache semantico Redis, fila PDF, circuit breaker.
- Python/FastAPI+Agno: process-document, chat RAG com fontes, summarize, compare.
- NeonDB serverless + pgvector: dados principais e embeddings.
- MongoDB: catalogo publico de livros.
- MinIO/S3: armazenamento de artefatos.

## Skills OpenCode (uso orientado)
- Identificar necessidade da tarefa e carregar skill especializada antes de implementar quando aplicavel:
  - `golang-pro` para Go
  - `fastapi-expert` para FastAPI/Agno
  - `api-designer` para contratos/endpoint design
  - `architecture-designer` para decisoes estruturais cross-service
