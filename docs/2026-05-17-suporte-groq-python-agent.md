# Suporte a Groq e Providers OpenAI-Compatibleis no Python-Agent

**Data:** 2026-05-17
**Servico:** `services/python-agent`
**Tipo:** Configuracao / Feature

## Contexto

O arquivo `.env.example` do python-agent ja mencionava a variavel `OPENAI_BASE_URL`, mas o codigo nao a utilizava. Todas as instanciacoes do cliente `OpenAI()` passavam apenas `api_key`, ignorando completamente a possibilidade de configurar um provider alternativo.

Usuarios que desejam usar Groq (ou qualquer provider compativel com a API OpenAI) nao conseguiam configurar o servico via ambiente, sendo obrigados a usar apenas a API oficial da OpenAI.

## Decisoes Tecnicas

### Menor mudanca possivel

A abordagem escolhida foi a de **menor alteracao necessaria**:

1. **Adicionar `OPENAI_BASE_URL` ao `Settings`** — unico campo novo na classe de configuracao.
2. **Passar `base_url` em todas as instanciacoes de `OpenAI()`** — 5 pontos no codigo (embedder + 4 servicos de dominio).
3. **Usar `base_url=None` quando vazio** — garante compatibilidade total com OpenAI padrao (comportamento original preservado).

### Por que nao abstrair o cliente LLM?

Uma abstracao mais elaborada (factory pattern, interface de provider, etc.) seria overkill para este cenario. A SDK da OpenAI ja suporta nativamente `base_url` para qualquer provider compativel, entao a mudanca minima atende o requisito sem adicionar complexidade.

### Embeddings com providers alternativos

Importante: providers como Groq **nao suportam o endpoint de embeddings**. Para evitar que o fluxo RAG quebre completamente, o `OpenAIEmbedder` implementa um **fallback seguro e seletivo**:

1. Quando `OPENAI_BASE_URL` esta configurado (provider alternativo) e a chamada de embeddings falha com erro tipico de modelo/endpoint nao suportado (ex: `NotFoundError`, mensagem contendo "does not exist", "not found", "404"), o servico ativa automaticamente embeddings mock deterministicos.
2. Um warning estruturado e registrado no log na primeira ocorrencia.
3. O fallback e **persistente na instancia** — apos ativado, chamadas subsequentes usam mock diretamente sem tentar a API novamente.
4. Para OpenAI padrao (`OPENAI_BASE_URL` vazio), **nenhum fallback e ativado** — erros sao propagados normalmente.
5. Erros genericos (timeout, rate limit, autenticacao) **nao ativam fallback** — sao propagados como `EmbeddingError`.

Isso permite que o pipeline RAG funcione integralmente com Groq para chat, usando embeddings mock para desenvolvimento e testes. Para embeddings reais em producao, use a API OpenAI padrao ou um provider que suporte ambos (chat + embeddings).

## Implementacao

### Arquivos alterados

| Arquivo | Mudanca |
|---------|---------|
| `app/core/config.py` | Adicionado campo `OPENAI_BASE_URL: str = ""` |
| `app/infrastructure/embeddings/openai_embedder.py` | Passa `base_url` ao criar cliente `OpenAI()`; adicionado fallback seguro para providers sem embeddings |
| `app/domain/rag_service.py` | Passa `base_url` ao criar cliente `OpenAI()` |
| `app/domain/summarize_service.py` | Passa `base_url` ao criar cliente `OpenAI()` |
| `app/domain/compare_service.py` | Passa `base_url` ao criar cliente `OpenAI()` |
| `app/domain/research_gap_service.py` | Passa `base_url` ao criar cliente `OpenAI()` |
| `.env.example` | Adicionadas instrucoes claras para Groq |
| `README.md` | Adicionada secao "Using Groq" com exemplos e nota sobre fallback de embeddings |
| `tests/test_config_base_url.py` | Testes de carregamento de `OPENAI_BASE_URL` |
| `tests/test_embedding_fallback.py` | Testes de fallback de embeddings para providers sem suporte |

### Padrao de codigo aplicado

Em todos os pontos de instanciacao do cliente OpenAI:

```python
base_url = self._settings.OPENAI_BASE_URL or None
client = OpenAI(
    api_key=self._settings.OPENAI_API_KEY,
    base_url=base_url,
)
```

O `or None` garante que string vazia seja convertida para `None`, que e o valor esperado pela SDK da OpenAI para usar o endpoint padrao.

## Testes Executados

### Novos testes criados

Arquivo: `tests/test_config_base_url.py`

Cobertura:
- `Settings` carrega `OPENAI_BASE_URL` corretamente (valor padrao e customizado)
- `OpenAIEmbedder` passa `base_url` ao cliente quando configurado
- `OpenAIEmbedder` passa `base_url=None` quando nao configurado
- `RAGService` passa `base_url` ao chamar LLM
- `SummarizeService` passa `base_url` ao chamar LLM
- `CompareService` passa `base_url` ao chamar LLM
- `ResearchGapService` passa `base_url` ao chamar LLM
- Servicos usam `base_url=None` quando `OPENAI_BASE_URL` e vazio

Arquivo: `tests/test_embedding_fallback.py`

Cobertura:
- `_is_provider_without_embeddings` reconhece padroes de erro corretos (NotFoundError, "does not exist", "not found", "404", "unsupported")
- `_is_provider_without_embeddings` ignora erros genericos (timeout, rate limit, autenticacao)
- `embed_query` cai para mock quando Groq retorna erro de modelo
- Fallback persiste na instancia (chamadas subsequentes nao tentam API)
- `embed_texts` com fallback no meio do batch retorna mock para restante
- Fallback gera warning estruturado no log
- OpenAI padrao (sem base_url) propaga erro em vez de fallback
- Erros genericos em provider alternativo sao propagados (nao engolidos)
- Modo mock original (sem API key) funciona como antes
- Embeddings mock sao deterministicos e diferentes para textos diferentes

### Comandos de teste

```bash
cd services/python-agent
pytest tests/test_config_base_url.py tests/test_embedding_fallback.py -v
```

## Comportamento: Antes vs Depois

### Antes
- `OPENAI_BASE_URL` existia no `.env.example` mas era ignorada pelo codigo
- Todas as chamadas LLM usavam exclusivamente a API oficial da OpenAI
- Nao era possivel usar Groq ou outros providers compativeis

### Depois
- `OPENAI_BASE_URL` e lida das variaveis de ambiente e aplicada em todas as chamadas
- OpenAI padrao funciona exatamente como antes (base_url vazio = None)
- Groq e qualquer provider OpenAI-compatible pode ser configurado via `.env`

### Exemplo de configuracao para Groq

```env
OPENAI_API_KEY=gsk_your_groq_key
OPENAI_MODEL=llama-3.3-70b-versatile
OPENAI_BASE_URL=https://api.groq.com/openai/v1
```

## Proximos Passos

- Avaliar se embeddings com provider alternativo sao necessarios (ex: usar OpenAI para embeddings + Groq para chat simultaneamente)
- Considerar adicionar validacao de modelo/provider no startup do servico
- Documentar no README principal do projeto a possibilidade de usar providers alternativos

## Por que nao foi necessario OpenSpec

Esta mudanca e uma **configuracao/bugfix** — a variavel `OPENAI_BASE_URL` ja existia no `.env.example` mas nunca foi implementada no codigo. Nao ha nova capacidade, breaking change, ou alteracao arquitetural. E simplesmente o preenchimento de uma lacuna entre documentacao e implementacao existente.
