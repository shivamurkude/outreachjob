"""Parse PDF/DOCX to extracted text and simple fields."""

import io
from pathlib import Path
from typing import Any

from pypdf import PdfReader
from docx import Document as DocxDocument

from app.core.exceptions import BadRequestError


def parse_pdf(content: bytes) -> dict[str, Any]:
    try:
        reader = PdfReader(io.BytesIO(content))
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return {"raw_text": text.strip(), "page_count": len(reader.pages)}
    except Exception as e:
        raise BadRequestError(f"Invalid PDF: {e}") from e


def parse_docx(content: bytes) -> dict[str, Any]:
    try:
        doc = DocxDocument(io.BytesIO(content))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        text = "\n".join(paragraphs)
        return {"raw_text": text.strip(), "paragraph_count": len(paragraphs)}
    except Exception as e:
        raise BadRequestError(f"Invalid DOCX: {e}") from e


def parse_resume(content: bytes, filename: str) -> dict[str, Any]:
    """Return extracted_fields dict (raw_text + metadata)."""
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return parse_pdf(content)
    if lower.endswith(".docx") or lower.endswith(".doc"):
        return parse_docx(content)
    raise BadRequestError("Unsupported format; use PDF or DOCX")
