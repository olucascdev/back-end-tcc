# Change: Replace mass indexing with on-demand public source retrieval

## Why
The current architecture pre-indexes 100+ public books from OpenAlex via a scheduled pipeline (public-indexer), storing artifacts in MinIO, metadata in MongoDB, and embeddings in NeonDB/pgvector. This is over-engineered for a TCC project: it consumes excessive storage, bandwidth, and processing for books that may never be queried. The user wants the agent to fetch only 3-5 relevant references on-demand when a question is asked, with fallback across multiple sources (OpenAlex API → alternate site → Google Books API).

## What Changes
- **BREAKING**: Remove scheduled mass-indexing pipeline from public-indexer
- **BREAKING**: Remove artifact storage (MinIO/S3) for public books
- **BREAKING**: Remove MongoDB catalog collection for public books
- **BREAKING**: Remove pre-computed embeddings for public books in NeonDB
- Add on-demand search adapter in python-agent that queries OpenAlex API in real-time
- Add fallback chain: OpenAlex → alternate download URL → Google Books API
- Add lightweight text extraction and embedding generation at query-time (3-5 results max)
- Add retrieval_mode="project_plus_public" support via on-demand search instead of pre-indexed vectors
- Keep public-indexer service alive but repurposed as a health-check / admin stub (or remove entirely in future change)

## Impact
- Affected specs: public-catalog-indexer, rag-agent-python
- Affected code: services/public-indexer/, services/python-agent/app/domain/retrieval/, services/python-agent/app/infrastructure/
- Affected infra: MinIO bucket `tcc-public-index` can be emptied; MongoDB collection `books` and `index_failures` can be dropped
