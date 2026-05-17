"""
Chunking de texto para geracao de embeddings.

Divide texto em segmentos com tamanho configuravel e sobreposicao
para preservar contexto entre chunks adjacentes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class TextChunk:
    """Representa um chunk de texto com metadados de posicao."""

    text: str
    chunk_index: int
    char_start: int
    char_end: int

    def to_dict(self) -> dict:
        """Converte para dict compativel com serializacao."""
        return {
            "text": self.text,
            "chunk_index": self.chunk_index,
            "char_start": self.char_start,
            "char_end": self.char_end,
        }


@dataclass
class ChunkingConfig:
    """Configuracao do chunker."""

    chunk_size: int = 1000
    overlap: int = 200
    min_chunk_size: int = 100


class TextChunker:
    """
    Divide texto em chunks com sobreposicao configuravel.

    Usa estrategia de splitting por paragrafos primeiro, depois
    por sentencas, e finalmente por palavras para respeitar
    o tamanho maximo do chunk.
    """

    def __init__(self, config: Optional[ChunkingConfig] = None) -> None:
        """
        Inicializa chunker com configuracao.

        Args:
            config: configuracao de chunking. Usa defaults se None.
        """
        self._config = config or ChunkingConfig()

    def chunk(self, text: str) -> list[TextChunk]:
        """
        Divide texto em chunks.

        Args:
            text: texto completo para dividir.

        Returns:
            Lista de TextChunk com texto e metadados de posicao.
        """
        if not text or not text.strip():
            return []

        # Normaliza espacos em branco
        text = self._normalize_whitespace(text)

        if len(text) <= self._config.chunk_size:
            # Texto cabe em um unico chunk
            return [
                TextChunk(
                    text=text,
                    chunk_index=0,
                    char_start=0,
                    char_end=len(text),
                )
            ]

        # Divide por paragrafos primeiro
        paragraphs = self._split_paragraphs(text)
        chunks = self._build_chunks_from_segments(paragraphs, text)

        logger.info("Texto dividido em %d chunks", len(chunks))
        return chunks

    def _normalize_whitespace(self, text: str) -> str:
        """Normaliza espacos em branco preservando quebras de paragrafo."""
        import re

        # Preserva quebras de linha duplas (paragrafos)
        # Normaliza espacos dentro de linhas
        lines = text.split("\n")
        normalized = []
        for line in lines:
            normalized.append(re.sub(r"[ \t]+", " ", line).strip())
        return "\n".join(normalized)

    def _split_paragraphs(self, text: str) -> list[tuple[str, int, int]]:
        """
        Divide texto em paragrafos com posicoes.

        Returns:
            Lista de (texto, char_start, char_end).
        """
        paragraphs = []
        current_start = 0

        # Split por quebras de linha duplas
        segments = text.split("\n\n")
        offset = 0

        for segment in segments:
            segment = segment.strip()
            if not segment:
                offset += len(segment) + 2  # +2 para "\n\n"
                continue

            # Encontra posicao real no texto original
            start = text.find(segment, offset)
            if start == -1:
                start = offset
            end = start + len(segment)

            paragraphs.append((segment, start, end))
            offset = end + 2

        return paragraphs

    def _build_chunks_from_segments(
        self,
        segments: list[tuple[str, int, int]],
        full_text: str,
    ) -> list[TextChunk]:
        """
        Constroi chunks a partir de segmentos respeitando tamanho maximo.

        Usa estrategia greedy: acumula segmentos ate atingir chunk_size,
        entao cria chunk e mantem overlap para o proximo.

        Args:
            segments: lista de (texto, start, end).
            full_text: texto original para referencia.

        Returns:
            Lista de TextChunk.
        """
        chunks = []
        current_text = ""
        current_start = 0
        chunk_index = 0

        for seg_text, seg_start, seg_end in segments:
            # Se segmento individual excede chunk_size, subdivide
            if len(seg_text) > self._config.chunk_size:
                # Finaliza chunk atual se houver
                if current_text:
                    chunks.append(
                        TextChunk(
                            text=current_text,
                            chunk_index=chunk_index,
                            char_start=current_start,
                            char_end=current_start + len(current_text),
                        )
                    )
                    chunk_index += 1

                # Subdivide segmento grande
                sub_chunks = self._split_large_segment(seg_text, seg_start)
                chunks.extend(sub_chunks)
                chunk_index = len(chunks)
                current_text = ""
                continue

            # Tenta adicionar segmento ao chunk atual
            if current_text:
                candidate = current_text + "\n\n" + seg_text
            else:
                candidate = seg_text

            if len(candidate) <= self._config.chunk_size:
                if not current_text:
                    current_start = seg_start
                current_text = candidate
            else:
                # Chunk atual esta cheio, cria e inicia novo com overlap
                chunks.append(
                    TextChunk(
                        text=current_text,
                        chunk_index=chunk_index,
                        char_start=current_start,
                        char_end=current_start + len(current_text),
                    )
                )
                chunk_index += 1

                # Aplica overlap: pega ultima parte do chunk anterior
                if (
                    self._config.overlap > 0
                    and len(current_text) > self._config.overlap
                ):
                    overlap_text = current_text[-self._config.overlap :]
                    # Encontra inicio de palavra para nao cortar no meio
                    overlap_text = self._find_word_boundary(overlap_text)
                    current_text = overlap_text + "\n\n" + seg_text
                    current_start = seg_start - len(overlap_text)
                else:
                    current_text = seg_text
                    current_start = seg_start

        # Adiciona chunk final
        if current_text and len(current_text) >= self._config.min_chunk_size:
            chunks.append(
                TextChunk(
                    text=current_text,
                    chunk_index=chunk_index,
                    char_start=current_start,
                    char_end=current_start + len(current_text),
                )
            )

        return chunks

    def _split_large_segment(self, text: str, base_offset: int) -> list[TextChunk]:
        """
        Subdivide segmento que excede chunk_size.

        Usa splitting por sentencas como estrategia secundaria.

        Args:
            text: segmento grande para dividir.
            base_offset: posicao base no texto original.

        Returns:
            Lista de TextChunk.
        """
        chunks = []
        sentences = self._split_sentences(text)

        current_text = ""
        current_start = base_offset
        chunk_index = 0

        for sent_text, sent_offset in sentences:
            if current_text:
                candidate = current_text + " " + sent_text
            else:
                candidate = sent_text

            if len(candidate) <= self._config.chunk_size:
                if not current_text:
                    current_start = base_offset + sent_offset
                current_text = candidate
            else:
                if current_text:
                    chunks.append(
                        TextChunk(
                            text=current_text,
                            chunk_index=chunk_index,
                            char_start=current_start,
                            char_end=current_start + len(current_text),
                        )
                    )
                    chunk_index += 1

                # Overlap para proximo chunk
                if (
                    self._config.overlap > 0
                    and len(current_text) > self._config.overlap
                ):
                    overlap_text = current_text[-self._config.overlap :]
                    overlap_text = self._find_word_boundary(overlap_text)
                    current_text = overlap_text + " " + sent_text
                    current_start = base_offset + sent_offset - len(overlap_text)
                else:
                    current_text = sent_text
                    current_start = base_offset + sent_offset

        if current_text and len(current_text) >= self._config.min_chunk_size:
            chunks.append(
                TextChunk(
                    text=current_text,
                    chunk_index=chunk_index,
                    char_start=current_start,
                    char_end=current_start + len(current_text),
                )
            )

        return chunks

    @staticmethod
    def _split_sentences(text: str) -> list[tuple[str, int]]:
        """
        Divide texto em sentencas com offsets.

        Usa pontuacao terminal (.!?) como delimitador.

        Args:
            text: texto para dividir.

        Returns:
            Lista de (sentenca, offset).
        """
        import re

        sentences = []
        # Pattern para encontrar finais de sentenca
        pattern = re.compile(r"(?<=[.!?])\s+")
        parts = pattern.split(text)

        offset = 0
        for part in parts:
            part = part.strip()
            if part:
                sentences.append((part, offset))
                offset += len(part) + 1

        return sentences

    @staticmethod
    def _find_word_boundary(text: str) -> str:
        """
        Encontra limite de palavra no inicio do texto.

        Se texto comeca no meio de uma palavra, avanca ate
        o proximo espaco.

        Args:
            text: texto para ajustar.

        Returns:
            Texto ajustado ao limite de palavra.
        """
        if not text:
            return text

        # Se comeca com espaco, remove leading spaces
        stripped = text.lstrip()
        if stripped:
            return stripped
        return text
