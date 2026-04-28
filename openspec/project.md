# Project Context

## Purpose
Construir backend poliglota para assistente de pesquisa academica com RAG. Escopo deste repositorio: planejamento e implementacao de backend com Go/Gin, Python/FastAPI+Agno, NeonDB+pgvector, Redis, MongoDB e MinIO/S3.

## Tech Stack
- Go + Gin (gateway/orquestracao de IA)
- Python + FastAPI + Agno (agente RAG)
- PostgreSQL serverless (NeonDB) + pgvector
- Redis (cache semantico e rate limiting state)
- MongoDB (catalogo publico de livros)
- MinIO/S3 (artefatos PDF/TXT)

## Project Conventions

### Code Style
- Nomes de variaveis, funcoes, classes, arquivos tecnicos e constantes em ingles.
- Comentarios no codigo em portugues do Brasil quando realmente necessarios.
- Evitar comentarios obvios; comentar apenas bloco nao trivial.
- Aplicar Clean Code: funcoes pequenas, responsabilidade unica, nomes claros, baixo acoplamento.

### Architecture Patterns
- Backend orientado a servicos separados por responsabilidade:
  - Go/Gin: rate limiting, cache semantico, fila PDF, circuit breaker, webhook status.
  - Python/FastAPI+Agno: process-document, chat RAG, summarize, compare.
- Arquitetura em camadas por servico: transport (HTTP), application/use cases, domain, infrastructure.
- Contratos internos versionados entre BFF -> Go -> Python.
- Resiliencia obrigatoria: timeout, retry com backoff e circuit breaker no gateway Go.

### Testing Strategy
- Go: testes unitarios para use cases e componentes de resiliencia; testes de integracao para handlers.
- Python: testes unitarios para servicos RAG e testes de integracao para endpoints FastAPI.
- Dados: validacao de migracoes e smoke tests para consultas vetoriais pgvector.
- Nao mergear feature sem validar cenarios principais da spec.

### Git Workflow
- Usar Conventional Commits em ingles (`feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`).
- Branch por feature/change-id do OpenSpec.
- Implementacao deve seguir fluxo SDD: proposal -> design -> tasks -> codigo.

## Domain Context
- Produto: assistente academico com RAG por projeto.
- Usuario faz upload de documentos, conversa com agente, recebe respostas com fontes rastreaveis.
- Sistema tambem indexa acervo publico (Gutenberg/Open Library) para ampliar base de conhecimento.

## Important Constraints
- Backend e frontend separados; este repositorio trata backend.
- NeonDB e banco principal serverless.
- MongoDB mantido apenas para catalogo publico.
- Cada feature/plano implementado deve gerar arquivo em `docs/*.md` em PT-BR descrevendo o que foi feito.
- Sempre usar OpenSpec para mudancas de capacidade, arquitetura ou comportamento.

## External Dependencies
- LLM provider (configuravel via ambiente)
- OpenAI/Agno SDK (quando aplicavel)
- Project Gutenberg (fonte publica)
- Open Library API (metadados publicos)
- Redis, NeonDB, MongoDB, MinIO/S3
