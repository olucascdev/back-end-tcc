"""
Testes das metricas Prometheus.

Verifica que counters e histograms sao incrementados corretamente.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.core import metrics


class TestMetricsLabels:
    """Testes de labels das metricas."""

    def test_indexer_runs_total_labels(self) -> None:
        """Verifica labels do counter de runs."""
        counter = metrics.public_indexer_runs_total
        assert "status" in counter._labelnames
        assert "source_filter" in counter._labelnames

    def test_run_duration_labels(self) -> None:
        """Verifica labels do histogram de duracao."""
        histogram = metrics.public_indexer_run_duration_seconds
        assert "status" in histogram._labelnames

    def test_books_fetched_labels(self) -> None:
        """Verifica labels do counter de livros buscados."""
        counter = metrics.public_books_fetched_total
        assert "source_provider" in counter._labelnames

    def test_books_indexed_labels(self) -> None:
        """Verifica labels do counter de livros indexados."""
        counter = metrics.public_books_indexed_total
        assert "source_provider" in counter._labelnames

    def test_failures_labels(self) -> None:
        """Verifica labels do counter de falhas."""
        counter = metrics.public_indexer_failures_total
        assert "stage" in counter._labelnames
        assert "source_provider" in counter._labelnames

    def test_embeddings_generated_labels(self) -> None:
        """Verifica labels do counter de embeddings."""
        counter = metrics.public_embeddings_generated_total
        assert "source_provider" in counter._labelnames


class TestMetricsIncrement:
    """Testes de incremento de metricas."""

    def test_increment_runs_total(self) -> None:
        """Verifica incremento do counter de runs."""
        metric = metrics.public_indexer_runs_total.labels(
            status="completed",
            source_filter="all",
        )
        # Salva valor inicial
        initial = metric._value.get()

        metric.inc()

        assert metric._value.get() == initial + 1

    def test_increment_books_fetched(self) -> None:
        """Verifica incremento do counter de livros buscados."""
        metric = metrics.public_books_fetched_total.labels(
            source_provider="gutenberg",
        )
        initial = metric._value.get()

        metric.inc()

        assert metric._value.get() == initial + 1

    def test_increment_books_indexed(self) -> None:
        """Verifica incremento do counter de livros indexados."""
        metric = metrics.public_books_indexed_total.labels(
            source_provider="openlibrary",
        )
        initial = metric._value.get()

        metric.inc()

        assert metric._value.get() == initial + 1

    def test_increment_failures(self) -> None:
        """Verifica incremento do counter de falhas."""
        metric = metrics.public_indexer_failures_total.labels(
            stage="embedding",
            source_provider="gutenberg",
        )
        initial = metric._value.get()

        metric.inc()

        assert metric._value.get() == initial + 1

    def test_increment_embeddings_generated(self) -> None:
        """Verifica incremento do counter de embeddings."""
        metric = metrics.public_embeddings_generated_total.labels(
            source_provider="gutenberg",
        )
        initial = metric._value.get()

        metric.inc(10)  # Incrementa por 10 embeddings

        assert metric._value.get() == initial + 10


class TestHistogramObservation:
    """Testes de observacao de histogram."""

    def test_observe_duration(self) -> None:
        """Verifica observacao de duracao no histogram."""
        histogram = metrics.public_indexer_run_duration_seconds.labels(
            status="completed",
        )

        # Observa um valor
        histogram.observe(5.0)

        # Verifica que o valor foi registrado
        # O histogram deve ter pelo menos uma observacao
        assert histogram._sum.get() >= 5.0
