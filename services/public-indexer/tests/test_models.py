"""
Testes dos modelos de dominio, focando em stable_key().

Verifica geracao de chaves estaveis para todas as fontes.
"""

from __future__ import annotations

import pytest

from app.domain.models import BookMetadata


class TestStableKeyGutenberg:
    """Testes de stable_key para Project Gutenberg."""

    def test_gutenberg_id_takes_priority(self) -> None:
        """Verifica que gutenberg_id tem maior prioridade."""
        book = BookMetadata(
            gutenberg_id="42",
            ol_key="/works/OL123W",
            source_id="W123",
            source_provider="openalex",
            title="Test Book",
        )

        assert book.stable_key() == "gutenberg:42"


class TestStableKeyOpenLibrary:
    """Testes de stable_key para Open Library."""

    def test_ol_key_second_priority(self) -> None:
        """Verifica que ol_key tem segunda prioridade."""
        book = BookMetadata(
            ol_key="/works/OL123W",
            source_id="W123",
            source_provider="openalex",
            title="Test Book",
        )

        assert book.stable_key() == "ol:/works/OL123W"


class TestStableKeyGenericSource:
    """Testes de stable_key para fontes genericas (source_provider + source_id)."""

    def test_openalex_stable_key(self) -> None:
        """Verifica stable_key para OpenAlex."""
        book = BookMetadata(
            source_id="W123456",
            source_provider="openalex",
            title="OpenAlex Paper",
            authors=["Author A"],
        )

        assert book.stable_key() == "openalex:W123456"

    def test_arxiv_stable_key(self) -> None:
        """Verifica stable_key para arXiv."""
        book = BookMetadata(
            source_id="2101.12345",
            source_provider="arxiv",
            title="arXiv Paper",
            authors=["Author B"],
        )

        assert book.stable_key() == "arxiv:2101.12345"

    def test_crossref_stable_key(self) -> None:
        """Verifica stable_key para Crossref."""
        book = BookMetadata(
            source_id="10.1000/test",
            source_provider="crossref",
            title="Crossref Paper",
            authors=["Author C"],
        )

        assert book.stable_key() == "crossref:10.1000/test"

    def test_missing_source_id_falls_back_to_hash(self) -> None:
        """Verifica que sem source_id faz fallback para hash."""
        book = BookMetadata(
            source_provider="openalex",
            title="Paper Without ID",
            authors=["Author"],
        )

        key = book.stable_key()
        assert key.startswith("hash:")
        assert "openalex" not in key

    def test_missing_source_provider_falls_back_to_hash(self) -> None:
        """Verifica que sem source_provider faz fallback para hash."""
        book = BookMetadata(
            source_id="W123",
            title="Paper Without Provider",
            authors=["Author"],
        )

        key = book.stable_key()
        assert key.startswith("hash:")


class TestStableKeyHashFallback:
    """Testes de stable_key com fallback hash."""

    def test_hash_based_on_title_and_authors(self) -> None:
        """Verifica que hash e baseado em titulo e autores."""
        book1 = BookMetadata(
            title="Same Title",
            authors=["Author A", "Author B"],
        )
        book2 = BookMetadata(
            title="Same Title",
            authors=["Author A", "Author B"],
        )

        # Mesmo titulo + autores = mesma chave
        assert book1.stable_key() == book2.stable_key()

    def test_hash_differs_for_different_titles(self) -> None:
        """Verifica que titulos diferentes geram hashes diferentes."""
        book1 = BookMetadata(
            title="Title One",
            authors=["Author"],
        )
        book2 = BookMetadata(
            title="Title Two",
            authors=["Author"],
        )

        assert book1.stable_key() != book2.stable_key()

    def test_hash_ignores_author_order(self) -> None:
        """Verifica que ordem dos autores nao afeta o hash."""
        book1 = BookMetadata(
            title="Same Title",
            authors=["Author A", "Author B"],
        )
        book2 = BookMetadata(
            title="Same Title",
            authors=["Author B", "Author A"],
        )

        assert book1.stable_key() == book2.stable_key()


class TestStableKeyPriority:
    """Testes de prioridade entre diferentes identificadores."""

    def test_full_priority_order(self) -> None:
        """Verifica ordem completa de prioridade."""
        # gutenberg_id > ol_key > source_provider:source_id > hash

        # Com todos os IDs, gutenberg_id vence
        book_all = BookMetadata(
            gutenberg_id="1",
            ol_key="/works/OL1W",
            source_id="W1",
            source_provider="openalex",
            title="Test",
        )
        assert book_all.stable_key() == "gutenberg:1"

        # Sem gutenberg_id, ol_key vence
        book_no_gutenberg = BookMetadata(
            ol_key="/works/OL1W",
            source_id="W1",
            source_provider="openalex",
            title="Test",
        )
        assert book_no_gutenberg.stable_key() == "ol:/works/OL1W"

        # Sem gutenberg_id e ol_key, source_provider:source_id vence
        book_generic = BookMetadata(
            source_id="W1",
            source_provider="openalex",
            title="Test",
        )
        assert book_generic.stable_key() == "openalex:W1"

        # Sem nenhum ID, fallback para hash
        book_hash = BookMetadata(
            title="Test",
            authors=["Author"],
        )
        assert book_hash.stable_key().startswith("hash:")
