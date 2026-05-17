## 1. Infrastructure & Cleanup
- [ ] 1.1 Document MinIO bucket `tcc-public-index` and MongoDB collections (`books`, `index_failures`) for manual cleanup
- [ ] 1.2 Disable public-indexer scheduled pipeline (set SYNC_INTERVAL_MINUTES=0 or comment cron setup)
- [ ] 1.3 Verify python-agent can run without public-indexer dependency

## 2. On-Demand Source Adapter (python-agent)
- [ ] 2.1 Create `app/infrastructure/sources/openalex_client.py` — search works by query, return top 5 with metadata + OA URL
- [ ] 2.2 Create `app/infrastructure/sources/unpaywall_client.py` — fallback to find OA PDF by DOI
- [ ] 2.3 Create `app/infrastructure/sources/google_books_client.py` — fallback for books without OA PDF
- [ ] 2.4 Create `app/domain/retrieval/public_source_retriever.py` — orchestrates fallback chain: OpenAlex → Unpaywall → Google Books
- [ ] 2.5 Implement lightweight download + text extraction for top-N results
- [ ] 2.6 Implement on-demand chunking + embedding for downloaded texts
- [ ] 2.7 Store generated embeddings in Redis with 1h TTL (not NeonDB)

## 3. Chat Integration
- [ ] 3.1 Update `app/api/v1/endpoints/chat.py` to call public_source_retriever when retrieval_mode="project_plus_public"
- [ ] 3.2 Merge project vectors + public source vectors for RAG context
- [ ] 3.3 Add sources from public retrieval to response payload with proper attribution
- [ ] 3.4 Add feature flag `ENABLE_PUBLIC_RETRIEVAL` (already exists, verify it works)

## 4. Gateway Fixes
- [ ] 4.1 Fix gateway 400 mapping for 404 responses from python-agent (distinguish 404 vs 400/422)
- [ ] 4.2 Verify gateway correctly forwards retrieval_mode to python-agent
- [ ] 4.3 Test end-to-end: curl gateway:8080/api/v1/chat with project_plus_public

## 5. Testing & Docs
- [ ] 5.1 Write unit tests for OpenAlex client (mock API responses)
- [ ] 5.2 Write unit tests for fallback chain
- [ ] 5.3 Write integration test for chat with public retrieval
- [ ] 5.4 Create `docs/on-demand-public-retrieval.md` in PT-BR explaining context, decisions, implementation, tests
