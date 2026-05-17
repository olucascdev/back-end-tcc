"""
Chunking de texto por tamanho com overlap.

Preserva informacao de pagina original para rastreabilidade nas fontes RAG.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class TextChunker:
    """Divide texto em chunks com overlap configuravel."""

    def chunk_text(
        self,
        text: str,
        chunk_size: int = 1000,
        overlap: int = 200,
        page_number: int = 1,
    ) -> list[dict]:
        """Divide texto em chunks mantendo contexto via overlap.

        Args:
            text: texto completo a ser dividido.
            chunk_size: tamanho maximo de cada chunk em caracteres.
            overlap: numero de caracteres sobrepostos entre chunks adjacentes.
            page_number: numero da pagina de origem para rastreabilidade.

        Returns:
            Lista de dicts com 'text', 'page_number' e 'chunk_index'.
        """
        if not text.strip():
            return []

        if overlap >= chunk_size:
            logger.warning(
                "Overlap (%d) >= chunk_size (%d); ajustando overlap para %d",
                overlap,
                chunk_size,
                chunk_size // 2,
            )
            overlap = chunk_size // 2

        chunks: list[dict] = []
        start = 0
        text_len = len(text)
        chunk_index = 0

        while start < text_len:
            end = start + chunk_size
            chunk_text = text[start:end]

            # Tenta quebrar em limite de palavra para nao cortar no meio
            if end < text_len:
                # Procura ultimo espaco dentro do chunk para corte limpo
                last_space = chunk_text.rfind(" ")
                if last_space > chunk_size * 0.5:  # so ajusta se nao perder muito texto
                    chunk_text = chunk_text[:last_space]
                    end = start + last_space

            chunks.append(
                {
                    "text": chunk_text.strip(),
                    "page_number": page_number,
                    "chunk_index": chunk_index,
                }
            )
            chunk_index += 1

            # Avanca posicao considerando overlap
            start = end - overlap
            if start <= start - 1:  # previne loop infinito
                break

        logger.debug("Texto chunked: %d chunks (pagina %d)", len(chunks), page_number)
        return chunks

    def chunk_pages(
        self,
        pages: list[dict],
        chunk_size: int = 1000,
        overlap: int = 200,
    ) -> list[dict]:
        """Aplica chunking em todas as paginas extraidas.

        Args:
            pages: lista de dicts com 'page_number' e 'text'.
            chunk_size: tamanho maximo de cada chunk.
            overlap: overlap entre chunks.

        Returns:
            Lista plana de chunks com metadata de pagina.
        """
        all_chunks: list[dict] = []
        for page in pages:
            page_chunks = self.chunk_text(
                text=page["text"],
                chunk_size=chunk_size,
                overlap=overlap,
                page_number=page["page_number"],
            )
            all_chunks.extend(page_chunks)
        return all_chunks
