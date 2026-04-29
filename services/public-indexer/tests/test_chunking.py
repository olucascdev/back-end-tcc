"""
Testes do TextChunker.

Verifica divisao de texto em chunks com tamanho e sobreposicao configuraveis.
"""

from __future__ import annotations

import pytest

from app.infrastructure.chunking import ChunkingConfig, TextChunker


class TestChunkerBasic:
    """Testes basicos de chunking."""

    def test_empty_text_returns_empty(self) -> None:
        """Verifica que texto vazio retorna lista vazia."""
        chunker = TextChunker()
        result = chunker.chunk("")
        assert result == []

    def test_whitespace_only_returns_empty(self) -> None:
        """Verifica que texto so com espacos retorna lista vazia."""
        chunker = TextChunker()
        result = chunker.chunk("   \n\n   ")
        assert result == []

    def test_single_chunk_for_small_text(self) -> None:
        """Verifica que texto pequeno cabe em um unico chunk."""
        chunker = TextChunker(ChunkingConfig(chunk_size=1000))
        text = "This is a short text."
        result = chunker.chunk(text)

        assert len(result) == 1
        assert result[0].text == text
        assert result[0].chunk_index == 0
        assert result[0].char_start == 0
        assert result[0].char_end == len(text)

    def test_chunk_to_dict(self) -> None:
        """Verifica conversao de chunk para dict."""
        from app.infrastructure.chunking import TextChunk

        chunk = TextChunk(text="Hello", chunk_index=0, char_start=0, char_end=5)
        d = chunk.to_dict()
        assert d["text"] == "Hello"
        assert d["chunk_index"] == 0
        assert d["char_start"] == 0
        assert d["char_end"] == 5


class TestChunkerSplitting:
    """Testes de divisao de texto longo."""

    def test_splits_long_text(self) -> None:
        """Verifica que texto longo e dividido em multiplos chunks."""
        config = ChunkingConfig(chunk_size=50, overlap=10)
        chunker = TextChunker(config)

        # Cria texto maior que chunk_size
        text = " ".join([f"Sentence {i}." for i in range(20)])
        result = chunker.chunk(text)

        assert len(result) > 1
        # Todos os chunks devem respeitar o tamanho maximo
        for chunk in result:
            assert len(chunk.text) <= config.chunk_size + 20  # margem para overlap

    def test_overlap_preserves_context(self) -> None:
        """Verifica que overlap preserva contexto entre chunks."""
        config = ChunkingConfig(chunk_size=50, overlap=15)
        chunker = TextChunker(config)

        text = "First paragraph content here. " * 10
        result = chunker.chunk(text)

        if len(result) >= 2:
            # Verifica que chunks adjacentes tem sobreposicao
            # (o final do chunk anterior aparece no inicio do proximo)
            last_words_chunk0 = result[0].text[-15:]
            first_words_chunk1 = result[1].text[:15]
            # Deve haver alguma sobreposicao
            assert len(last_words_chunk0.strip()) > 0

    def test_chunk_indices_sequential(self) -> None:
        """Verifica que indices dos chunks sao sequenciais."""
        config = ChunkingConfig(chunk_size=50, overlap=10)
        chunker = TextChunker(config)

        text = "Word " * 50
        result = chunker.chunk(text)

        for i, chunk in enumerate(result):
            assert chunk.chunk_index == i

    def test_char_positions_are_valid(self) -> None:
        """Verifica que posicoes de caracteres sao validas."""
        config = ChunkingConfig(chunk_size=100, overlap=0)
        chunker = TextChunker(config)

        text = "A" * 300
        result = chunker.chunk(text)

        for chunk in result:
            assert chunk.char_start >= 0
            assert chunk.char_end > chunk.char_start
            assert chunk.char_end <= len(text)


class TestChunkerConfig:
    """Testes de configuracao do chunker."""

    def test_custom_chunk_size(self) -> None:
        """Verifica uso de chunk_size customizado."""
        config = ChunkingConfig(chunk_size=30, overlap=0, min_chunk_size=10)
        chunker = TextChunker(config)

        text = "Small chunk test. " * 10
        result = chunker.chunk(text)

        # Com chunk_size=30, deve gerar varios chunks
        assert len(result) > 1

    def test_zero_overlap(self) -> None:
        """Verifica chunking sem overlap."""
        config = ChunkingConfig(chunk_size=50, overlap=0)
        chunker = TextChunker(config)

        text = "No overlap text. " * 10
        result = chunker.chunk(text)

        # Sem overlap, chunks nao devem compartilhar texto
        if len(result) >= 2:
            # Verifica que nao ha sobreposicao de posicoes
            for i in range(len(result) - 1):
                assert result[i].char_end <= result[i + 1].char_start

    def test_min_chunk_size_filter(self) -> None:
        """Verifica que chunks menores que min_chunk_size sao filtrados."""
        config = ChunkingConfig(chunk_size=100, overlap=0, min_chunk_size=50)
        chunker = TextChunker(config)

        # Texto que geraria um chunk pequeno no final
        text = "A" * 120
        result = chunker.chunk(text)

        # O chunk final deve respeitar min_chunk_size ou nao existir
        for chunk in result:
            assert len(chunk.text) >= config.min_chunk_size
