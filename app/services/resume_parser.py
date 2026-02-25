"""Parse PDF/DOCX to extracted text and simple fields."""

import io
from typing import Any

from docx import Document as DocxDocument
from pypdf import PdfReader

from app.core.exceptions import BadRequestError
from app.core.logging import get_logger

log = get_logger(__name__)


def parse_pdf(content: bytes) -> dict[str, Any]:
    log.debug("parse_pdf", size=len(content))
    try:
        reader = PdfReader(io.BytesIO(content))
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        out = {"raw_text": text.strip(), "page_count": len(reader.pages)}
        log.debug("parse_pdf_ok", page_count=out["page_count"])
        return out
    except Exception as e:
        log.warning("parse_pdf_failed", reason=str(e)[:100])
        raise BadRequestError(f"Invalid PDF: {e}") from e


def parse_docx(content: bytes) -> dict[str, Any]:
    log.debug("parse_docx", size=len(content))
    try:
        doc = DocxDocument(io.BytesIO(content))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        text = "\n".join(paragraphs)
        out = {"raw_text": text.strip(), "paragraph_count": len(paragraphs)}
        log.debug("parse_docx_ok", paragraph_count=out["paragraph_count"])
        return out
    except Exception as e:
        log.warning("parse_docx_failed", reason=str(e)[:100])
        raise BadRequestError(f"Invalid DOCX: {e}") from e


def parse_resume(content: bytes, filename: str) -> dict[str, Any]:
    """Return extracted_fields dict (raw_text + metadata)."""
    log.debug("parse_resume", filename=filename, size=len(content))
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return parse_pdf(content)
    if lower.endswith(".docx") or lower.endswith(".doc"):
        return parse_docx(content)
    log.warning("parse_resume_unsupported", filename=filename)
    raise BadRequestError("Unsupported format; use PDF or DOCX")
