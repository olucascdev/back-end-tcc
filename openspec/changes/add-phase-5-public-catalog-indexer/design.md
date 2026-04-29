## Context
A Fase 5 implementa o servico `public-indexer` responsavel por ingerir acervo publico (Open Library, Project Gutenberg) e produzir embeddings rastreaveis no NeonDB/pgvector. Este e um change cross-service que envolve `public-indexer`, MongoDB, MinIO/S3, NeonDB e Redis.

## Goals / Non-Goals
- Goals:
  - Pipeline fim-a-fim executavel local sem intervencao manual por item
  - Catalogo publico sincronizado em MongoDB com deduplicacao previsivel
  - Artefatos armazenados em MinIO/S3 com rastreabilidade
  - Embeddings publicos persistidos com metadata obrigatoria de origem
  - Reexecucao segura sem duplicidade vetorial
  - Observabilidade completa por job
- Non-Goals:
  - Consumo do acervo publico no endpoint de chat RAG (futura fase)
  - Mudancas no frontend/BFF
  - Novas features academicas de resumo/comparacao

## Decisions
- **Boundary**: `public-indexer` possui responsabilidade exclusiva sobre indexacao publica. Nao compartilha logica de ingestao com `python-agent`.
- **Formato de artefato**: Prioridade configuravel com padrao txt > epub > pdf. Motivo: txt tem menor custo de extracao, epub mantem estrutura semantica, pdf e ultimo recurso.
- **Idempotencia**: Fingerprint composto por `source_id + checksum + chunk_version`. Permite reprocessamento controlado quando conteudo muda (checksum diferente) e evita duplicidade quando conteudo e igual.
- **Lock distribuido**: Redis com TTL baseado no `SYNC_INTERVAL_MINUTES` (ex: 2x o intervalo). Alternativa: lock em PostgreSQL (advisory lock) descartada para manter o servico desacoplado de detalhes de schema do banco principal.
- **Metadata de embeddings publicos**: Schema JSONB obrigatorio com `source_type=public_library`, `source_provider`, `source_id`, `artifact_key`, `checksum`. Pipeline bloqueia escrita antes de atingir o banco se metadata estiver incompleta.
- **Tabela vetorial**: Padronizar em `document_embeddings`. Motivo: runtime ja usa este nome; migracao 002 (`embeddings`) sera corrigida/renomeada em preflight para alinhar contrato. Nao criar tabela separada para manter busca por similaridade unificada.

## Risks / Trade-offs
- **Risco**: Divergencia de nome de tabela (`embeddings` vs `document_embeddings`) pode causar falha de runtime se nao resolvida em preflight -> Mitigacao: Feature 5.0 obrigatoria antes de qualquer escrita vetorial.
- **Risco**: Volume de dados publico pode gerar custo inesperado no NeonDB serverless -> Mitigacao: batching configuravel e throttling no download.
- **Risco**: APIs publicas (Open Library/Gutenberg) possuem rate limits e indisponibilidade -> Mitigacao: retry com backoff exponencial, jitter e isolamento de falha por item.
- **Risco**: Lock Redis nao e forte garantia em caso de split-brain -> Mitigacao: TTL curto e heartbeat opcional em versao futura.

## Migration Plan
1. Executar preflight 5.0: validar schema, renomear/criar tabela `document_embeddings`, corrigir migracao 002.
2. Aplicar migracao de schema no NeonDB (padronizacao de tabela e novos indices).
3. Fazer deploy do `public-indexer` com feature flag de escrita vetorial desabilitada ate validacao de schema.
4. Habilitar escrita apos smoke test em ambiente de staging.
5. Rollback: reverter para versao anterior do servico; embeddings ja gerados permanecem na tabela unificada.

## Open Questions
- Qual o tamanho maximo de artefato que devemos aceitar? (limit de download/upload)
- Devemos manter fila de dead-letter para itens que falham apos esgotar retry?
- Qual a estrategia de rotacao/delecao de artefatos antigos no MinIO?
