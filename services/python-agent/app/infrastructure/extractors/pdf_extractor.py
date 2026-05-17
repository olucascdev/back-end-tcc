"""
Extrator de texto de arquivos PDF.

Usa PyPDF2 para extracao pagina a pagina. Retorna lista de dicts
com page_number e text para cada pagina do documento.
"""

from __future__ import annotations

import logging
from io import BytesIO

from PyPDF2 import PdfReader
from PyPDF2.errors import PdfReadError

logger = logging.getLogger(__name__)


class PDFExtractor:
    """Extrai texto estruturado por pagina de um PDF."""

    def extract_text(self, file_bytes: bytes) -> list[dict]:
        """Extrai texto de cada pagina do PDF.

        Args:
            file_bytes: conteudo binario do arquivo PDF.

        Returns:
            Lista de dicts com 'page_number' (1-based) e 'text'.

        Raises:
            ValueError: se o arquivo nao for um PDF valido.
        """
        try:
            reader = PdfReader(BytesIO(file_bytes))
        except PdfReadError as exc:
            logger.error("Arquivo PDF invalido ou corrompido: %s", exc)
            raise ValueError(f"PDF invalido ou corrompido: {exc}") from exc

        pages: list[dict] = []
        for idx, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            pages.append(
                {
                    "page_number": idx,
                    "text": text.strip(),
                }
            )

        logger.info("PDF extraido: %d paginas", len(pages))
        return pages
