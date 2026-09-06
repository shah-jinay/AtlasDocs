"""Parsing and normalization (blueprint section 9.3).

Produces a flat list of `Unit`s -- the smallest structural piece the
chunker is allowed to split on (a paragraph, a heading, a page fragment) --
each carrying the page/section metadata that must survive all the way to a
citation. Validates the declared MIME type against what the parser
actually finds, per the checklist item "do not trust only the filename
extension."
"""
import re
import unicodedata
from dataclasses import dataclass
from io import BytesIO

import docx
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.ingestion.errors import ParseError, ScannedPdfError, UnsupportedMimeTypeError

_MIN_CHARS_PER_PAGE_TO_COUNT_AS_TEXT = 20


@dataclass(frozen=True)
class Unit:
    text: str
    page_start: int | None
    page_end: int | None
    section_path: str | None


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Collapse runs of horizontal whitespace but keep paragraph breaks.
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_pdf(data: bytes) -> list[Unit]:
    try:
        reader = PdfReader(BytesIO(data))
    except PdfReadError as exc:
        raise ParseError(f"Could not open PDF: {exc}") from exc

    if reader.is_encrypted:
        raise ParseError("PDF is password-protected")

    units: list[Unit] = []
    pages_with_text = 0
    for page_index, page in enumerate(reader.pages, start=1):
        try:
            raw = page.extract_text() or ""
        except Exception as exc:  # pypdf can raise assorted parser errors per-page
            raise ParseError(f"Failed to extract text from page {page_index}: {exc}") from exc
        text = _normalize(raw)
        if len(text) >= _MIN_CHARS_PER_PAGE_TO_COUNT_AS_TEXT:
            pages_with_text += 1
        for paragraph in _split_paragraphs(text):
            units.append(Unit(text=paragraph, page_start=page_index, page_end=page_index, section_path=None))

    if not reader.pages:
        raise ParseError("PDF has no pages")
    if pages_with_text == 0:
        raise ScannedPdfError()
    return units


def parse_docx(data: bytes) -> list[Unit]:
    try:
        document = docx.Document(BytesIO(data))
    except Exception as exc:  # python-docx raises bare Exception/PackageNotFoundError
        raise ParseError(f"Could not open DOCX: {exc}") from exc

    units: list[Unit] = []
    section_path: str | None = None
    for para in document.paragraphs:
        text = _normalize(para.text)
        if not text:
            continue
        style = (para.style.name or "").lower() if para.style else ""
        if style.startswith("heading"):
            section_path = text
            continue
        units.append(Unit(text=text, page_start=None, page_end=None, section_path=section_path))

    if not units:
        raise ParseError("DOCX contains no extractable paragraph text")
    return units


def parse_plain_text(data: bytes) -> list[Unit]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ParseError(f"Could not decode file as UTF-8 text: {exc}") from exc

    text = _normalize(text)
    if not text:
        raise ParseError("File is empty")

    units: list[Unit] = []
    section_path: str | None = None
    for paragraph in _split_paragraphs(text):
        heading_match = re.match(r"^(#{1,6})\s+(.*)$", paragraph)
        if heading_match:
            section_path = heading_match.group(2).strip()
            continue
        units.append(Unit(text=paragraph, page_start=None, page_end=None, section_path=section_path))
    return units


def _split_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in text.split("\n\n") if p.strip()]


_PARSERS = {
    "application/pdf": parse_pdf,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": parse_docx,
    "text/plain": parse_plain_text,
    "text/markdown": parse_plain_text,
}


def parse(*, mime_type: str, data: bytes) -> list[Unit]:
    parser = _PARSERS.get(mime_type)
    if parser is None:
        raise UnsupportedMimeTypeError(f"No parser registered for MIME type '{mime_type}'")
    return parser(data)
