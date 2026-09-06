import pytest

from app.ingestion.errors import ParseError, UnsupportedMimeTypeError
from app.ingestion.parser import parse


def test_plain_text_parses_paragraphs():
    text = b"First paragraph.\n\nSecond paragraph."
    units = parse(mime_type="text/plain", data=text)
    assert [u.text for u in units] == ["First paragraph.", "Second paragraph."]


def test_markdown_headings_become_section_path():
    text = b"# Introduction\n\nBody text under the heading."
    units = parse(mime_type="text/markdown", data=text)
    assert len(units) == 1
    assert units[0].section_path == "Introduction"
    assert units[0].text == "Body text under the heading."


def test_empty_text_file_raises_parse_error():
    with pytest.raises(ParseError):
        parse(mime_type="text/plain", data=b"   \n\n  ")


def test_non_utf8_bytes_raise_parse_error():
    with pytest.raises(ParseError):
        parse(mime_type="text/plain", data=b"\xff\xfe\x00\x01invalid")


def test_unsupported_mime_type_raises():
    with pytest.raises(UnsupportedMimeTypeError):
        parse(mime_type="application/zip", data=b"whatever")
