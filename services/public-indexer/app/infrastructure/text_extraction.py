"""
Extracao de texto de artefatos de livros.

Suporta TXT, EPUB e PDF com fallbacks graciosos quando
bibliotecas opcionais nao estao disponiveis.
"""

from __future__ import annotations

import logging
import zipfile
from io import BytesIO
from typing import Optional

logger = logging.getLogger(__name__)


class TextExtractor:
    """Extrai texto puro de artefatos em diferentes formatos."""

    def extract_from_txt(self, content: bytes) -> str:
        """
        Decodifica arquivo TXT como UTF-8.

        Args:
            content: bytes do arquivo.

        Returns:
            Texto decodificado.
        """
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            # Fallback para latin-1 (sempre funciona)
            logger.warning("UTF-8 falhou, usando latin-1 como fallback")
            return content.decode("latin-1")

    def extract_from_epub(self, content: bytes) -> str:
        """
        Extrai texto de arquivo EPUB.

        Tenta usar ebooklib primeiro; se indisponivel, faz parsing
        basico via zip extraindo arquivos HTML/XHTML.

        Args:
            content: bytes do arquivo EPUB.

        Returns:
            Texto extraido.
        """
        # Tenta ebooklib primeiro
        try:
            import ebooklib
            from ebooklib import epub

            book = epub.read_epub(BytesIO(content))
            texts = []
            for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
                texts.append(item.get_content().decode("utf-8", errors="ignore"))
            result = "\n".join(texts)
            # Remove tags HTML basicas
            return self._strip_html(result)
        except ImportError:
            logger.debug("ebooklib indisponivel, usando fallback zip")
            return self._epub_fallback_zip(content)
        except Exception as exc:
            logger.warning("Falha ao extrair EPUB com ebooklib: %s", exc)
            return self._epub_fallback_zip(content)

    def extract_from_pdf(self, content: bytes) -> str:
        """
        Extrai texto de arquivo PDF.

        Tenta PyPDF2 primeiro; se indisponivel, tenta pdfplumber;
        se ambos indisponiveis, retorna string vazia com log.

        Args:
            content: bytes do arquivo PDF.

        Returns:
            Texto extraido.
        """
        # Tenta PyPDF2
        try:
            from PyPDF2 import PdfReader

            reader = PdfReader(BytesIO(content))
            texts = []
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    texts.append(page_text)
            return "\n".join(texts)
        except ImportError:
            pass
        except Exception as exc:
            logger.warning("Falha ao extrair PDF com PyPDF2: %s", exc)

        # Tenta pdfplumber
        try:
            import pdfplumber

            with pdfplumber.open(BytesIO(content)) as pdf:
                texts = []
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        texts.append(page_text)
                return "\n".join(texts)
        except ImportError:
            pass
        except Exception as exc:
            logger.warning("Falha ao extrair PDF com pdfplumber: %s", exc)

        logger.error("Nenhuma biblioteca PDF disponivel (PyPDF2, pdfplumber)")
        return ""

    def extract(self, artifact_key: str, content: bytes, fmt: str) -> str:
        """
        Dispatch de extracao por formato.

        Args:
            artifact_key: chave do artefato (para logging).
            content: bytes do conteudo.
            fmt: formato do arquivo (txt, epub, pdf).

        Returns:
            Texto extraido.

        Raises:
            ValueError se formato nao suportado.
        """
        fmt_lower = fmt.lower().strip()
        logger.info("Extraindo texto: key=%s, format=%s", artifact_key, fmt_lower)

        if fmt_lower == "txt":
            return self.extract_from_txt(content)
        elif fmt_lower == "epub":
            return self.extract_from_epub(content)
        elif fmt_lower == "pdf":
            return self.extract_from_pdf(content)
        else:
            # Tenta como TXT como fallback generico
            logger.warning("Formato nao suportado '%s', tentando como TXT", fmt_lower)
            return self.extract_from_txt(content)

    @staticmethod
    def _strip_html(text: str) -> str:
        """Remove tags HTML basicas de um texto."""
        import re

        # Remove tags HTML
        text = re.sub(r"<[^>]+>", " ", text)
        # Normaliza espacos em branco
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @staticmethod
    def _epub_fallback_zip(content: bytes) -> str:
        """
        Fallback basico para EPUB: extrai arquivos HTML do ZIP.

        EPUB e essencialmente um ZIP com arquivos XHTML/HTML.

        Args:
            content: bytes do arquivo EPUB.

        Returns:
            Texto extraido dos arquivos HTML.
        """
        texts = []
        try:
            with zipfile.ZipFile(BytesIO(content)) as zf:
                for name in zf.namelist():
                    if name.endswith((".html", ".xhtml", ".htm")):
                        try:
                            html_content = zf.read(name).decode(
                                "utf-8", errors="ignore"
                            )
                            texts.append(html_content)
                        except Exception:
                            continue
        except zipfile.BadZipFile:
            logger.error("Arquivo EPUB corrompido (ZIP invalido)")
            return ""

        raw = "\n".join(texts)
        return TextExtractor._strip_html(raw)
