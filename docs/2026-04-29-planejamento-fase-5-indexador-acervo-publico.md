# Planejamento Fase 5 - Indexador de acervo publico

## Contexto
A Fase 5 amplia a base de conhecimento do backend com ingestao de acervo publico, mantendo escopo estrito em indexacao e prontidao de dados. Nesta fase, nao entra consumo direto desse acervo no chat RAG. O foco e construir pipeline confiavel, rastreavel e idempotente para popular MongoDB, MinIO/S3 e NeonDB/pgvector com livros publicos.

Escopo da fase:
- pipeline agendado de indexacao publica
- sincronizacao de metadados em MongoDB (`books`)
- persistencia de artefatos em MinIO/S3
- geracao e persistencia de embeddings publicos no NeonDB/pgvector
- idempotencia, retry seguro e observabilidade operacional

Fora de escopo da fase:
- uso do acervo publico no endpoint de chat
- mudancas de frontend/BFF
- novas features academicas de resumo/comparacao

## Decisoes tecnicas
- Servico principal: `services/public-indexer` (Python), com responsabilidade exclusiva de indexacao publica.
- Fonte de metadados: Open Library e Project Gutenberg.
- Catalogo publico em MongoDB (`books`) como estado operacional do indexador.
- Artefatos de origem (TXT/PDF/EPUB quando aplicavel) em MinIO/S3 para rastreabilidade e reprocessamento.
- Embeddings no NeonDB/pgvector com metadados obrigatorios de origem:
  - `source_type=public_library`
  - `source_provider`
  - `source_id`
  - `artifact_key`
  - `checksum`
- Estrategia de idempotencia baseada em fingerprint de conteudo (`source_id + checksum + chunk_version`).
- Agendamento com lock distribuido (Redis) para evitar execucoes concorrentes duplicadas.
- Fluxo SDD obrigatorio via OpenSpec com change dedicado da fase:
  - `openspec/changes/add-phase-5-public-catalog-indexer/proposal.md`
  - `openspec/changes/add-phase-5-public-catalog-indexer/tasks.md`
  - `openspec/changes/add-phase-5-public-catalog-indexer/design.md`

## Implementacao

### Feature 5.0 - Preflight tecnico e alinhamento de schema
Objetivo:
- eliminar ambiguidades antes do pipeline principal.

Escopo tecnico:
- validar e padronizar schema vetorial usado em runtime e migracoes.
- revisar divergencia atual entre nomes de tabela vetorial (`embeddings` vs `document_embeddings`) e definir contrato unico.
- definir formato padrao de metadata para embeddings publicos.
- definir politicas de deduplicacao por livro e por chunk.

Criterios de aceite:
- contrato de dados documentado e unificado.
- pipeline bloqueia escrita com metadata incompleta.

### Feature 5.1 - Bootstrap real do servico public-indexer
Objetivo:
- substituir estrutura planejada por servico executavel.

Escopo tecnico:
- implementar estrutura base em camadas (`api`, `application`, `domain`, `infrastructure`, `core`).
- criar endpoints administrativos:
  - `GET /health`
  - `POST /admin/index/run`
  - `GET /admin/index/jobs/{job_id}`
- configurar `Settings` e lifecycle de conexoes (MongoDB, PostgreSQL, MinIO, Redis).

Criterios de aceite:
- servico sobe localmente e health responde com dependencias.
- execucao manual de job inicia e reporta status.

### Feature 5.2 - Ingestao de catalogo publico (metadados)
Objetivo:
- sincronizar catalogo publico no MongoDB com deduplicacao previsivel.

Escopo tecnico:
- implementar clientes de fonte para Open Library e Project Gutenberg.
- normalizar campos (titulo, autores, idioma, assuntos, ids de origem, formatos).
- aplicar upsert em `books` com controle de estado:
  - novo item: `indexed=false`
  - item alterado: `indexed=false` e limpeza de status de indexacao anterior quando aplicavel
- manter chaves de deduplicacao estaveis (`gutenberg_id`, `ol_key`, fallback hash).

Criterios de aceite:
- ciclo de sync nao duplica livro logico.
- itens novos e atualizados ficam corretamente sinalizados para indexacao.

### Feature 5.3 - Download e armazenamento de artefatos
Objetivo:
- garantir rastreabilidade completa do conteudo indexado.

Escopo tecnico:
- selecionar melhor formato disponivel por estrategia configuravel (preferencia: txt > epub > pdf).
- baixar artefatos com timeout e retry seguro.
- persistir no MinIO/S3 com chave deterministica (`provider/source_id/version`).
- calcular `checksum` para controle de mudanca de conteudo.
- persistir referencia de artefato no MongoDB.

Criterios de aceite:
- todo item apto a indexacao possui `artifact_key` e `checksum` validos.
- falhas de download nao quebram lote inteiro (isolamento por item).

### Feature 5.4 - Geracao de embeddings publicos
Objetivo:
- transformar acervo em base vetorial consultavel e rastreavel.

Escopo tecnico:
- extrair texto dos artefatos.
- executar chunking com parametros configuraveis.
- gerar embeddings em lote.
- persistir vetores no NeonDB/pgvector com metadata completa de origem.
- atualizar item no MongoDB para `indexed=true` e preencher `indexed_at` ao concluir.

Criterios de aceite:
- embeddings gravados com `source_type=public_library` em 100% dos registros da fase.
- `indexed` e `indexed_at` atualizados apenas apos persistencia vetorial bem-sucedida.

### Feature 5.5 - Idempotencia, retry e agendamento
Objetivo:
- tornar pipeline seguro para reexecucao e operacao continua.

Escopo tecnico:
- evitar duplicacao vetorial por fingerprint de conteudo.
- implementar retry com backoff exponencial e jitter para erros transientes.
- implementar registro de falhas finais por item para reprocessamento posterior.
- adicionar agendamento periodico via `SYNC_INTERVAL_MINUTES`.
- usar lock distribuido Redis por job para evitar overlap de execucoes.

Criterios de aceite:
- reexecucao do mesmo lote nao cria duplicidade de embeddings.
- falha transiente recupera automaticamente dentro da politica de retry.
- execucao concorrente e bloqueada por lock valido.

### Feature 5.6 - Observabilidade e operacao
Objetivo:
- permitir auditoria, diagnostico e governanca do pipeline.

Escopo tecnico:
- metricas obrigatorias:
  - `public_indexer_runs_total`
  - `public_indexer_run_duration_seconds`
  - `public_books_fetched_total`
  - `public_books_indexed_total`
  - `public_indexer_failures_total`
- logs estruturados com `request_id`, `job_id`, `source_provider`, `source_id`, `stage`.
- relatorio de fim de job com totais: novos, atualizados, ignorados, indexados, falhos.

Criterios de aceite:
- metricas expostas e consumiveis.
- cada item processado possui trilha de log por etapa.

## Testes executados
Este documento representa planejamento da Fase 5. Nao ha execucao de codigo nesta entrega.

Testes obrigatorios durante execucao:
- Unitarios (public-indexer):
  - normalizacao de metadados por fonte
  - chave de deduplicacao
  - seletor de formato de artefato
  - fingerprint/idempotency key
  - parser e serializacao de metadata vetorial
- Integracao (pipeline):
  - Open Library/Gutenberg (mock) -> MongoDB (`books`)
  - download -> MinIO -> persistencia `artifact_key`
  - chunking/embeddings -> NeonDB/pgvector -> update `indexed/indexed_at`
- Resiliencia:
  - retry em timeout de fonte
  - retry em falha transiente de storage
  - isolamento de falha por item no lote
  - lock distribuido evitando job concorrente
- Regressao de dados:
  - reprocessamento do mesmo item sem duplicar embeddings
  - item alterado por checksum gera nova versao de indexacao controlada

## Cronograma recomendado (Semanas 16-18)
1. Semana 16: OpenSpec + preflight tecnico + bootstrap do servico + sync de metadados.
2. Semana 17: download de artefatos + embeddings publicos + atualizacao de status no MongoDB.
3. Semana 18: idempotencia/retry/agendamento + observabilidade + bateria final de testes + conclusao da fase.

## Definition of Done da Fase 5
- Pipeline fim-a-fim executa local sem intervencao manual por item.
- Colecao `books` atualizada com `indexed`, `indexed_at` e identificadores de origem consistentes.
- Embeddings publicos persistidos com `source_type=public_library` e metadata obrigatoria.
- Reexecucao de job nao gera duplicidade vetorial.
- Metricas e logs permitem auditoria completa por job.
- OpenSpec da fase validado com `openspec validate add-phase-5-public-catalog-indexer --strict`.
- Documentacao de features e conclusao publicada em `docs/`.

## Artefatos de documentacao previstos
- `docs/2026-04-29-planejamento-fase-5-indexador-acervo-publico.md`
- `docs/2026-04-29-feature-5-1-bootstrap-public-indexer.md`
- `docs/2026-04-29-feature-5-2-ingestao-catalogo-publico.md`
- `docs/2026-04-29-feature-5-3-artefatos-minio.md`
- `docs/2026-04-29-feature-5-4-embeddings-public-library.md`
- `docs/2026-04-29-feature-5-5-idempotencia-retry-agendamento.md`
- `docs/2026-04-29-fase-5-conclusao-indexador-acervo-publico.md`

## Proximos passos
1. Criar e validar change OpenSpec `add-phase-5-public-catalog-indexer`.
2. Implementar na ordem: 5.0 -> 5.1 -> 5.2 -> 5.3 -> 5.4 -> 5.5 -> 5.6.
3. Gerar um documento por feature concluida com evidencias de teste.
4. Consolidar fechamento da fase com metricas operacionais e riscos residuais.
