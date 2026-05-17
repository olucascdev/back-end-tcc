## Context
O gateway Go ja possui spec de cache semantico definida no change `add-backend-go-python-rag-neondb`, mas sem implementacao. Phase 3 entrega cache Redis funcional, invalidacao por versao de documento, observabilidade e benchmark. Rate limiting atual e in-memory (fase 2), o que limita deploy multi-instancia.

## Goals / Non-Goals
- Goals:
  - Cache semantico Redis funcional no path de chat com TTL configuravel
  - Invalidacao automatica de cache quando documentos do projeto sao atualizados
  - Metricas e logs de cache para monitoramento
  - Benchmark com evidencia de ganhos de performance
  - (Opcional) Rate limiting em Redis para multi-instancia
- Non-Goals:
  - Nao alterar pipeline RAG do Python agent
  - Nao implementar cache distribuido para outros endpoints (so chat na fase 3)
  - Nao substituir NeonDB como fonte da verdade de embeddings

## Decisions
- **Embedding para cache**: usar mesmo embedding model do RAG para consistencia semantica. Gateway chama Python agent `/v1/embed` ou usa modelo local leve (ex: all-MiniLM-L6-v2 via ONNX) para gerar embedding da query antes de buscar no cache.
  - Alternativa considerada: hash exato da query → rejeitado pois nao captura equivalencia semantica.
  - Alternativa considerada: embedding no gateway via modelo local → preferido se latencia adicional for < 10ms; senao, delegar ao Python agent.
- **Armazenamento em Redis**: usar Redis Hash com campo de embedding + RediSearch para busca vetorial por similaridade. Se RediSearch nao disponivel, fallback para abordagem de chave composta `cache:{project_id}:{embedding_hash}` com threshold de similaridade pre-computado.
  - Alternativa considerada: RedisJSON → rejeitado pois nao suporta busca vetorial nativa sem modulo adicional.
  - Alternativa considerada: cache em memoria LRU no Go → rejeitado pois nao sobrevive a restart e nao compartilha entre instancias.
- **Invalidacao por versao**: incluir `document_version` na chave de cache (`cache:{project_id}:{version}:{query_hash}`). Quando versao incrementa, chaves antigas tornam-se inacessiveis naturalmente. TTL cuida da limpeza.
  - Alternativa considerada: SCAN + DELETE explicito → rejeitado por custo operacional e risco de bloqueio em projetos com muitas entries.
- **Rate limiting Redis (opcional)**: usar Lua script atomico para token bucket em Redis. Manter feature flag para rollout gradual.
  - Alternativa considerada: Redis + go-redis `RateLimiter` → preferido por simplicidade e manutencao.

## Risks / Trade-offs
- **Redis como dependencia adicional**: se Redis cair, chat deve funcionar sem cache (fallback transparente). Mitigacao: timeout curto no cache (50ms), fallback para miss.
- **Embedding no gateway adiciona latencia**: se modelo local for lento, delegar ao Python agent. Mitigacao: benchmark do embedding local antes de decidir.
- **Invalidacao por versao pode invalidar cache demais**: se apenas 1 documento de 50 for atualizado, todo cache do projeto e perdido. Mitigacao: na fase 4, refinar para invalidacao por documento especifico.
- **RediSearch modulo pode nao estar disponivel no Redis do docker-compose**: usar Redis Stack image (`redis/redis-stack`) que inclui RediSearch e RedisJSON.

## Migration Plan
1. Adicionar Redis Stack ao docker-compose (substituir Redis vanilla se necessario).
2. Implementar cache semantico com feature flag `SEMANTIC_CACHE_ENABLED=false` por default.
3. Rollout: habilitar em staging, validar metricas, habilitar em producao.
4. Rollback: desabilitar feature flag, cache bypass automatico.
5. (Opcional) Rate limiting Redis: feature flag `RATE_LIMIT_BACKEND=memory` por default, migrar gradualmente.

## Open Questions
- Qual imagem Redis usar no docker-compose? Redis vanilla ou Redis Stack?
- O embedding para cache deve ser gerado no gateway (modelo local) ou delegado ao Python agent?
- Threshold de similaridade para cache hit: 0.95, 0.90, ou configuravel?
- TTL default do cache: 1h, 4h, 24h? Depende da frequencia de atualizacao de documentos.
