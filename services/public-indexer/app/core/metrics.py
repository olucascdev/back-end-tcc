"""
Metricas Prometheus para o public-indexer.

Define counters, histograms e gauges para monitoramento
do pipeline de indexacao.
"""

from __future__ import annotations

from prometheus_client import Counter, Histogram

# Contador de execucoes do indexer
public_indexer_runs_total = Counter(
    "public_indexer_runs_total",
    "Total de execucoes do public-indexer",
    ["status", "source_filter"],
)

# Histogram de duracao das execucoes
public_indexer_run_duration_seconds = Histogram(
    "public_indexer_run_duration_seconds",
    "Duracao das execucoes do public-indexer em segundos",
    ["status"],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600],
)

# Contador de livros buscados do catalogo
public_books_fetched_total = Counter(
    "public_books_fetched_total",
    "Total de livros buscados do catalogo publico",
    ["source_provider"],
)

# Contador de livros indexados com sucesso
public_books_indexed_total = Counter(
    "public_books_indexed_total",
    "Total de livros indexados com sucesso",
    ["source_provider"],
)

# Contador de falhas no pipeline
public_indexer_failures_total = Counter(
    "public_indexer_failures_total",
    "Total de falhas no pipeline de indexacao",
    ["stage", "source_provider"],
)

# Contador de embeddings gerados
public_embeddings_generated_total = Counter(
    "public_embeddings_generated_total",
    "Total de embeddings gerados para o acervo publico",
    ["source_provider"],
)
