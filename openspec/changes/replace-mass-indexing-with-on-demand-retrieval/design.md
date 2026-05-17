## Context
The current system pre-indexes public academic sources (OpenAlex) through a scheduled pipeline. For a TCC project, this creates unnecessary complexity: ~100 books are downloaded, chunked, and embedded regardless of user queries. The user wants a simpler model where references are fetched on-demand.

## Goals / Non-Goals
- Goals:
  - Fetch 3-5 relevant public references per user query
  - Support fallback across multiple sources
  - Minimize infrastructure (no mass storage of public artifacts)
  - Keep response time acceptable (<5s for on-demand retrieval + response)
- Non-Goals:
  - Full-text search over millions of papers
  - Persistent caching of public source embeddings
  - Scheduled background jobs for indexing

## Decisions
- Decision: Use OpenAlex API as primary source (free, no key, academic focus)
  - Alternatives considered: Semantic Scholar (requires key), CrossRef (metadata only), arXiv API (limited scope)
  - Rationale: OpenAlex has abstracts, DOI, and open-access links; no API key needed
- Decision: Fallback chain: OpenAlex → Unpaywall / DOI resolver → Google Books API
  - Alternatives considered: Single source only
  - Rationale: OpenAlex sometimes lacks download URLs; Unpaywall finds OA PDFs by DOI; Google Books covers non-OA books
- Decision: Generate embeddings at query-time for top-K results only
  - Alternatives considered: Pre-index all results
  - Rationale: With 3-5 results per query, embedding cost is negligible; eliminates need for persistent public vector store
- Decision: Store retrieved public chunks in a short-lived in-memory cache (Redis) with 1-hour TTL
  - Alternatives considered: Persist in NeonDB
  - Rationale: Avoids vector store bloat; same query within 1h reuses embeddings

## Risks / Trade-offs
- [Slower first query] → Mitigation: top-K results are small; embedding model is fast; parallelize source calls
- [Source API rate limits] → Mitigation: implement simple in-memory rate limit tracking; fallback chain reduces single-source dependency
- [No persistent public knowledge base] → Mitigation: acceptable for TCC scope; project documents remain persisted

## Migration Plan
1. Implement on-demand adapter in python-agent (new code, no breaking change to project-only mode)
2. Update gateway to route project_plus_public correctly
3. Disable public-indexer scheduled jobs (set SYNC_INTERVAL_MINUTES=0 or remove cron)
4. Clean up MinIO bucket and MongoDB collections (manual step, documented)
5. Remove public-indexer service from docker-compose (future change)

## Open Questions
- Should we keep the public-indexer service as a no-op stub or remove it entirely?
- Is 1-hour Redis TTL sufficient for public source cache?
