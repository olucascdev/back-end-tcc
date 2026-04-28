# Plano completo de implementacao do backend por fases

## Contexto
Este plano define a execucao completa do backend do assistente academico com RAG. Escopo inclui apenas backend real: Go/Gin, Python/FastAPI+Agno, NeonDB+pgvector, Redis, MongoDB e MinIO/S3. Frontend e BFF ficam fora deste repositorio.

## Decisoes tecnicas
- Arquitetura poliglota por responsabilidade:
  - Go/Gin: gateway de IA, resiliencia e orquestracao.
  - Python/FastAPI+Agno: processamento RAG e features semanticas.
- NeonDB serverless como banco principal para dados relacionais e vetoriais (pgvector).
- MongoDB apenas para catalogo publico de livros.
- Redis para cache semantico e estado de rate limiting.
- MinIO/S3 para armazenamento de artefatos PDF/TXT.
- Fluxo SDD obrigatorio com OpenSpec para cada mudanca relevante.

## Implementacao

### Regras gerais (obrigatorias em todas as fases)
- Criar docs em `docs/*.md` para cada feature/plano implementado.
- Comentarios de codigo em PT-BR.
- Nomenclatura de codigo em ingles (variaveis, funcoes, classes e identificadores).
- Commits em ingles seguindo Conventional Commits.
- Clean Code + arquitetura em camadas por servico (transport/application/domain/infrastructure).
- Usar skills especializadas quando aplicavel: `golang-pro`, `fastapi-expert`, `api-designer`, `architecture-designer`.

### Fase 0 - Fundacao tecnica (Semanas 1-2)
Objetivo: preparar base de implementacao com contratos e dados.

Entregas:
- Estrutura de servicos: `services/go-gateway`, `services/python-agent`, `services/public-indexer`, `infra`.
- Contratos internos v1 entre BFF -> Go -> Python.
- Payload de webhook para status de documento (`pending`, `processing`, `ready`, `error`).
- Schema inicial NeonDB para `users`, `projects`, `documents`, `conversations`, `agent_sessions`, `embeddings`.
- Convention de observabilidade (logs estruturados com `request_id`, `project_id`, `user_id`, `document_id`).

Criterios de aceite:
- Ambiente sobe local.
- Migracoes executam sem erro.
- Healthcheck de servicos disponivel.

### Fase 1 - MVP RAG por projeto (Semanas 3-6)
Objetivo: fluxo ponta-a-ponta funcional com fontes.

Entregas:
- Python `POST /process-document`: chunking + embeddings + persistencia pgvector.
- Python `POST /chat`: resposta com fontes rastreaveis (`filename`, `page`).
- Go gateway minimo: timeout/retry e roteamento para Python.
- Persistencia de conversas no NeonDB.

Criterios de aceite:
- Upload processado e consultavel no chat.
- Resposta com fonte obrigatoria quando houver contexto.
- Retorno explicito de limitacao quando contexto insuficiente.

### Fase 2 - Resiliencia e escala no Go (Semanas 7-9)
Objetivo: robustez operacional do gateway.

Entregas:
- Rate limiting por usuario (token bucket).
- Circuit breaker para dependencia Python.
- Fila concorrente de PDF com workers/goroutines/channels.
- Webhook para notificar BFF ao concluir/falhar processamento.

Criterios de aceite:
- Gateway continua responsivo sob carga.
- Falha do Python nao derruba fluxo HTTP.

### Fase 3 - Cache semantico e performance (Semanas 10-11)
Objetivo: reduzir latencia e chamadas repetidas ao agente.

Entregas:
- Cache semantico Redis por `project_id + normalized_question_hash`.
- Politica de TTL e invalidacao por novo documento processado.
- Medicao de ganho de performance (baseline vs cache ativo).

Criterios de aceite:
- Reducao de latencia p95 em perguntas repetidas.
- Reducao de chamadas ao Python em cenarios equivalentes.

### Fase 4 - Features academicas avancadas (Semanas 12-15)
Objetivo: ampliar valor academico do produto.

Entregas:
- Python `POST /summarize-document` com saida estruturada: objetivo, metodologia, resultados, conclusao.
- Python `POST /compare-documents` com comparacao estruturada e orientada a tema.
- Sugestao de lacunas de pesquisa baseada no corpus do projeto.

Criterios de aceite:
- Saidas estaveis e estruturadas.
- Comparacao com rastreabilidade de fontes.

### Fase 5 - Indexador de acervo publico (Semanas 16-18)
Objetivo: enriquecer base com documentos publicos.

Entregas:
- Pipeline agendado: Gutenberg/OpenLibrary -> MongoDB -> MinIO/S3 -> NeonDB/pgvector.
- Metadados em `books` no MongoDB (`indexed`, `indexed_at`, identificadores de origem).
- Embeddings com `source_type=public_library`.
- Idempotencia e retry seguro.

Criterios de aceite:
- Ciclo completo sem duplicidade de embeddings.
- Itens indexados marcados corretamente no catalogo.

### Fase 6 - Qualidade, avaliacao e hardening (Semanas 19-20)
Objetivo: consolidar qualidade tecnica e academica para TCC.

Entregas:
- Testes unitarios e integracao em Go e Python.
- Testes de carga para latencia/throughput e comportamento de resiliencia.
- Avaliacao RAG com metricas: faithfulness, answer relevancy, context recall, context precision.
- Ajustes finais de seguranca e observabilidade.

Criterios de aceite:
- Metricas coletadas e reproduziveis.
- Requisitos principais de performance e confiabilidade atendidos.

### Backlog pos-fases (opcional)
- Grafo de referencias entre documentos.
- Exportacao de anotacoes em formato ABNT/APA.
- Re-ranking hibrido (lexical + vetorial).

## Testes executados
- Neste momento, este documento registra plano de implementacao.
- Validacao de estrutura OpenSpec ja executada no change principal:
  - `openspec validate add-backend-go-python-rag-neondb --strict`

## Proximos passos
1. Aprovar este plano como baseline de execucao.
2. Iniciar Fase 0 com tarefas curtas (1-2 dias) e checklists objetivos.
3. A cada feature concluida, criar novo arquivo em `docs/` com contexto, decisoes, implementacao, testes e proximos passos.
