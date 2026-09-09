"""PDF Extraction utility for Document module (A10-2)."""

from __future__ import annotations

import re


class PDFTextExtractionError(ValueError):
    """Raised when PDF lacks a text layer or is malformed."""


def extract_pdf_sections(pdf_bytes: bytes, filename: str = "brochure.pdf") -> list[tuple[int, str, str]]:
    """Extract section-aware text blocks from a brochure PDF preserving page_number, section_title, and equipment tables.

    Returns:
        List of (page_number, section_title, content) tuples.

    Raises:
        PDFTextExtractionError: If PDF scan lacks a text-layer.
    """
    if not pdf_bytes:
        raise PDFTextExtractionError("PDF file is empty")

    sections: list[tuple[int, str, str]] = []

    # Attempt parsing with standard PDF streams or text markers
    try:
        text_content = pdf_bytes.decode("utf-8", errors="ignore")
        if not text_content or len(text_content) < 20:
            text_content = pdf_bytes.decode("latin-1", errors="ignore")
    except Exception as exc:
        raise PDFTextExtractionError(f"Could not parse PDF content: {exc}") from exc

    # Check for text layer streams (/Text, BT ... ET, or plain text)
    bt_blocks = re.findall(r"BT\s*(.*?)\s*ET", text_content, re.DOTALL)
    extracted_text_pieces = []

    for block in bt_blocks:
        strings = re.findall(r"\((.*?)\)", block)
        if strings:
            extracted_text_pieces.append(" ".join(strings))

    full_extracted = " ".join(extracted_text_pieces).strip()

    if not full_extracted:
        ascii_matches = re.findall(r"[\x20-\x7E\u00A0-\u024F]{4,}", text_content)
        filtered_ascii = [s for s in ascii_matches if not s.startswith("/") and not s.startswith("<<")]
        if len(filtered_ascii) > 5:
            full_extracted = "\n".join(filtered_ascii)

    if not full_extracted or len(full_extracted.strip()) < 5:
        raise PDFTextExtractionError(f"PDF '{filename}' scan without text layer is not supported")

    pages_raw = re.split(r"(?:Trang\s+\d+|Page\s+\d+|\f)", full_extracted, flags=re.IGNORECASE)

    current_page = 1
    for page_text in pages_raw:
        clean_page = page_text.strip()
        if not clean_page:
            continue

        clean_lower = clean_page.lower()
        # Match both accented and unaccented keywords
        if any(kw in clean_lower for kw in ["trang bị", "trang bi", "thông số", "thong so", "bảng giá", "bang gia"]):
            sections.append((current_page, "Bảng trang bị", clean_page))
        else:
            lines = clean_page.split("\n")
            section_title = lines[0][:100] if lines else "Tổng quan"
            sections.append((current_page, section_title, clean_page))

        current_page += 1

    return sections
