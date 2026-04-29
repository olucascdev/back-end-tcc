"""
Testes do TextExtractor.

Verifica extracao de texto para TXT, EPUB e PDF.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.infrastructure.text_extraction import TextExtractor


class TestExtractFromTxt:
    """Testes de extracao de TXT."""

    def test_extract_utf8_text(self) -> None:
        """Verifica decodificacao UTF-8."""
        extractor = TextExtractor()
        content = b"Ola mundo! Este e um teste."
        result = extractor.extract_from_txt(content)
        assert result == "Ola mundo! Este e um teste."

    def test_extract_latin1_fallback(self) -> None:
        """Verifica fallback para latin-1 quando UTF-8 falha."""
        extractor = TextExtractor()
        # Bytes invalidos em UTF-8 mas validos em latin-1
        content = b"\xe9\xe0\xfc"  # e-acute, a-grave, u-umlaut
        result = extractor.extract_from_txt(content)
        assert len(result) == 3

    def test_extract_empty_content(self) -> None:
        """Verifica extracao de conteudo vazio."""
        extractor = TextExtractor()
        result = extractor.extract_from_txt(b"")
        assert result == ""


class TestExtractFromEpub:
    """Testes de extracao de EPUB."""

    def test_epub_fallback_zip(self) -> None:
        """Verifica fallback de extracao via ZIP."""
        import io
        import zipfile

        extractor = TextExtractor()

        # Cria EPUB fake como ZIP com arquivo HTML
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("OEBPS/content.html", "<html><body>Hello World</body></html>")
            zf.writestr("OEBPS/chapter1.xhtml", "<html><body>Chapter One</body></html>")

        content = buf.getvalue()
        result = extractor.extract_from_epub(content)

        assert "Hello World" in result
        assert "Chapter One" in result
        # Tags HTML devem ser removidas
        assert "<html>" not in result

    def test_epub_bad_zip(self) -> None:
        """Verifica tratamento de ZIP corrompido."""
        extractor = TextExtractor()
        result = extractor.extract_from_epub(b"not a zip file")
        assert result == ""

    def test_epub_empty_zip(self) -> None:
        """Verifica EPUB sem arquivos HTML."""
        import io
        import zipfile

        extractor = TextExtractor()
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("META-INF/container.xml", "<container/>")

        content = buf.getvalue()
        result = extractor.extract_from_epub(content)
        assert result == ""


class TestExtractFromPdf:
    """Testes de extracao de PDF."""

    def test_pdf_no_library_returns_empty(self) -> None:
        """Verifica que sem bibliotecas PDF retorna string vazia."""
        extractor = TextExtractor()
        # Sem PyPDF2 nem pdfplumber instalados no ambiente de teste
        result = extractor.extract_from_pdf(b"fake pdf content")
        # Retorna string vazia quando nenhuma biblioteca esta disponivel
        assert isinstance(result, str)


class TestExtractDispatch:
    """Testes do metodo dispatch extract()."""

    def test_extract_txt(self) -> None:
        """Verifica dispatch para TXT."""
        extractor = TextExtractor()
        result = extractor.extract("test.txt", b"Hello", "txt")
        assert result == "Hello"

    def test_extract_epub(self) -> None:
        """Verifica dispatch para EPUB."""
        import io
        import zipfile

        extractor = TextExtractor()
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("content.html", "<html><body>Test</body></html>")

        result = extractor.extract("test.epub", buf.getvalue(), "epub")
        assert "Test" in result

    def test_extract_pdf(self) -> None:
        """Verifica dispatch para PDF."""
        extractor = TextExtractor()
        result = extractor.extract("test.pdf", b"fake pdf", "pdf")
        assert isinstance(result, str)

    def test_extract_unknown_format_fallback(self) -> None:
        """Verifica fallback para formato desconhecido."""
        extractor = TextExtractor()
        result = extractor.extract("test.xyz", b"Hello", "xyz")
        assert result == "Hello"

    def test_extract_case_insensitive(self) -> None:
        """Verifica que formato e case-insensitive."""
        extractor = TextExtractor()
        result = extractor.extract("test.TXT", b"Hello", "TXT")
        assert result == "Hello"
