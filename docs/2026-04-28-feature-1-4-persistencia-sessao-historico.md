# Feature 1.4 - Persistencia de sessao e historico

## Contexto

A Feature 1.3 implementou o pipeline RAG completo com historico de conversas, mas a classe `SessionHistory` armazenava mensagens apenas em memoria (dicionario Python). Isso gerava tres problemas criticos:

1. **Perda de historico ao reiniciar o servico** — todas as conversas ativas eram descartadas, impedindo continuidade entre sessoes.
2. **Sem compartilhamento entre instancias** — em deploy com multiplas replicas do Python-Agent, cada instancia mantinha seu proprio historico isolado.
3. **Contexto LLM sem persistencia** — o historico usado para enriquecer prompts do LLM desaparecia, forcando o usuario a repetir contexto a cada reinicializacao.

Esta feature resolve:
- substituir `SessionHistory` em memoria por repositorios persistidos no NeonDB
- criar tabela `agent_sessions` para metadata de sessao (memory JSONB)
- criar tabela `conversations` para historico completo de mensagens com fontes
- integrar repositorios ao `RAGService` mantendo contrato de API inalterado
- limitar historico carregado para contexto LLM (ultimas 6 mensagens = 3 trocas)
- serializar fontes como JSONB para armazenamento eficiente

## Decisoes tecnicas

### Separacao em dois repositorios

Duas tabelas com responsabilidades distintas:

| Tabela | Finalidade | Granularidade |
|---|---|---|
| `agent_sessions` | Metadata da sessao, memoria agregada | 1 row por `session_id` |
| `conversations` | Historico completo de mensagens | 1 row por mensagem |

**Motivo**: `agent_sessions` armazena estado agregado da sessao (topicos discutidos, contagem de turnos, preferencias) enquanto `conversations` registra cada interacao individual. Separacao permite:
- atualizar memoria da sessao sem inserir nova linha de conversa
- consultar historico cronologico sem carregar metadata desnecessario
- aplicar TTL ou arquivamento em `conversations` sem afetar sessoes ativas

### `session_repository.py` — get_or_create_session

Padrao upsert manual: `SELECT` primeiro, `INSERT` se nao existir.

```sql
-- SELECT para buscar sessao existente
SELECT session_id, project_id::text, memory, created_at
FROM agent_sessions WHERE session_id = %s

-- INSERT para criar nova sessao
INSERT INTO agent_sessions (session_id, project_id, memory)
VALUES (%s, %s, %s)
RETURNING session_id, project_id::text, memory, created_at
```

**Motivo**: NeonDB (PostgreSQL serverless) nao suporta `INSERT ... ON CONFLICT` com `RETURNING` de forma consistente em cold starts. Padrao SELECT-then-INSERT evita race condition porque `session_id` e gerado pelo cliente (Go gateway) antes da chamada.

### `session_repository.py` — update_session_memory

Atualiza campo `memory` (JSONB) e `updated_at` via trigger.

```sql
UPDATE agent_sessions
SET memory = %s, updated_at = NOW()
WHERE session_id = %s
```

Validacao: `rowcount == 0` levanta `ValueError` — sessao deve existir antes de atualizar memoria.

### `conversation_repository.py` — save_message

Insere mensagem com fontes serializadas via `psycopg2.extras.Json`.

```sql
INSERT INTO conversations (project_id, session_id, role, content, sources)
VALUES (%s, %s, %s, %s, %s)
```

**Serializacao JSONB para fontes**: campo `sources` usa tipo `JSONB` do PostgreSQL. Vantagens:
- indexacao nativa em campos JSON (possibilidade futura de buscar por documento citado)
- validacao automatica de estrutura JSON pelo banco
- compressao interna eficiente para arrays pequenos
- compatibilidade com Pydantic `model_dump()` → `Json()` sem transformacao adicional

Fontes vazias (`None` ou `[]`) sao normalizadas para `Json([])` — nunca `NULL` no banco.

### `conversation_repository.py` — get_conversation_history

Consulta com `ORDER BY created_at DESC LIMIT %s` e inversao em Python.

```sql
SELECT role, content, sources, created_at
FROM conversations
WHERE session_id = %s
ORDER BY created_at DESC
LIMIT %s
```

**Limite de historico para contexto LLM**: default `limit=10`, mas `RAGService` usa `limit=6` (3 trocas user/assistant). Motivo:
- cada mensagem consome tokens no prompt do LLM
- 6 mensagens = ~500-800 tokens de historico, dentro do budget de contexto
- trocas mais antigas tem relevancia decrescente para a pergunta atual
- limite configuravel permite ajuste futuro sem mudanca de schema

**Inversao de ordem**: banco retorna mais recente primeiro (DESC), Python inverte com `reversed()` para ordem cronologica (mais antigo primeiro). Necessario porque a API OpenAI espera mensagens em ordem temporal.

### Integracao no RAGService

`RAGService.chat()` agora executa 10 passos (antes 8):

```
1. get_or_create_session(session_id, project_id)  ← NOVO
2. save_message(role="user", content=message)     ← NOVO (era in-memory)
3. embed_query(message)
4. search_similar_by_project(project_id, embedding)
5. Se sem contexto → save_message(role="assistant") + retorna limitacao
6. _build_context(chunks)
7. _call_llm(context, question, session_id)
     └─ get_conversation_history(session_id, limit=6)  ← NOVO (era in-memory)
8. _extract_sources(chunks)
9. save_message(role="assistant", sources=sources)    ← NOVO
10. retorna ChatResponse
```

**Remocao do `SessionHistory` em memoria**: classe `SessionHistory` foi removida do `rag_service.py`. Toda persistencia agora passa pelos repositorios.

### Schema do banco (Migration 001)

Tabelas criadas em `001_create_base_tables.sql`:

**`conversations`**:
- `id UUID` PK
- `project_id UUID` FK → projects (CASCADE DELETE)
- `session_id VARCHAR(255)` — identificador de sessao (gerado pelo gateway Go)
- `role VARCHAR(20)` CHECK IN ('user', 'assistant')
- `content TEXT` — texto da mensagem
- `sources JSONB DEFAULT '[]'` — fontes citadas (apenas assistant)
- `created_at TIMESTAMPTZ`

**`agent_sessions`**:
- `id UUID` PK
- `project_id UUID` FK → projects (CASCADE DELETE)
- `session_id VARCHAR(255)` UNIQUE
- `memory JSONB DEFAULT '{}'` — metadata agregada da sessao
- `created_at TIMESTAMPTZ`
- `updated_at TIMESTAMPTZ` (trigger automatico)

## Implementacao

### Arquivos criados

#### `app/infrastructure/database/session_repository.py` (novo)
- `get_or_create_session(session_id, project_id, settings)` — busca ou cria sessao no banco
- `update_session_memory(session_id, memory, settings)` — atualiza campo memory JSONB
- Usa `psycopg2` sync com context manager `get_db_connection()`
- Logging estruturado para criacao e atualizacao de sessoes

#### `app/infrastructure/database/conversation_repository.py` (novo)
- `save_message(session_id, project_id, role, content, sources, settings)` — persiste mensagem
- `get_conversation_history(session_id, limit, settings)` — recupera historico ordenado
- Serializacao de fontes via `psycopg2.extras.Json`
- Normalizacao `sources or []` para evitar NULL no banco

#### `tests/test_session_persistence.py` (novo)
- 11 testes cobrindo ambos os repositorios
- Classes de teste: `TestGetOrCreateSession`, `TestUpdateSessionMemory`, `TestSaveMessage`, `TestGetConversationHistory`
- Mock de `get_db_connection` para testes sem banco real
- Cenarios: criacao, leitura, atualizacao, erro de sessao inexistente, fontes vazias, limite de historico, ordem cronologica

### Arquivos modificados

#### `app/domain/rag_service.py` (modificado)
- Removida classe `SessionHistory` (memoria)
- Adicionados imports: `conversation_repository`, `session_repository`
- `RAGService.chat()` agora chama repositorios em vez de `self.session_history`
- `_call_llm()` carrega historico via `conversation_repository.get_conversation_history()`
- Persistencia de mensagens do usuario e assistant em pontos corretos do fluxo
- Fontes serializadas com `src.model_dump()` antes de salvar

#### `infra/migrations/postgres/001_create_base_tables.sql` (existente, referencia)
- Tabelas `conversations` e `agent_sessions` ja definidas nesta migration
- Coluna `sources JSONB` com default `'[]'`
- Trigger `trg_agent_sessions_updated_at` para atualizacao automatica

## Testes executados

### Suite completa: 83/83 passando

```
======================== 83 passed, 1 warning in 0.73s =========================
```

### Distribuicao por arquivo

| Arquivo de teste | Testes | Cobertura |
|---|---|---|
| `test_api_v1.py` | 6 | Health endpoints, stubs de documents/summarize/compare |
| `test_contracts_v1.py` | 38 | Validacao, serializacao e roundtrip JSON de todos os schemas Pydantic |
| `test_process_document.py` | 14 | Pipeline completo de processamento, componentes unitarios, cenarios de erro |
| `test_chat_rag.py` | 14 | RAGService com/sem contexto, formato de fontes, erro LLM, endpoint API |
| `test_session_persistence.py` | 11 | Repositorios de sessao e conversas, mock de banco |

### Cenarios testados em `test_session_persistence.py`

#### SessionRepository
- `test_creates_new_session_when_not_exists`: SELECT retorna None → INSERT executado, sessao criada com memory vazia
- `test_returns_existing_session`: SELECT retorna row → apenas 1 query executada, memory preservada
- `test_updates_memory_successfully`: UPDATE executado com commit, rowcount = 1
- `test_raises_when_session_not_found`: rowcount = 0 → `ValueError` com mensagem "nao encontrada"

#### ConversationRepository
- `test_saves_user_message`: INSERT executado para role=user sem fontes
- `test_saves_assistant_message_with_sources`: INSERT com fontes JSONB nao nulo
- `test_saves_message_with_empty_sources`: `sources=None` convertido para `Json([])`
- `test_returns_history_in_chronological_order`: banco retorna DESC, Python inverte para ASC — mais antigo primeiro
- `test_respects_limit_parameter`: LIMIT passado na query restringe resultados
- `test_returns_empty_list_for_new_session`: sessao sem conversas retorna `[]`
- `test_history_includes_sources`: historico preserva fontes quando presentes

### Warning conhecido
- PyPDF2 emite `DeprecationWarning` recomendando migracao para `pypdf`. Nao afeta funcionalidade.

## Proximos passos

1. **Feature 1.5 - Observabilidade minima do MVP**: adicionar metrics (latencia, error rate), structured logging com correlation ID, health check com dependencias (DB, pgvector, OpenAI), tracing basico de requests Go → Python.
2. Implementar endpoint `GET /sessions/{session_id}/history` para frontend consultar historico completo.
3. Adicionar indice em `conversations(session_id, created_at)` para otimizar queries de historico em escala.
4. Avaliar estrategia de TTL para conversas antigas (arquivamento ou soft delete).
5. Implementar summarize real de documentos (`POST /documents/summarize`).
6. Implementar comparacao tematica entre documentos (`POST /documents/compare`).
