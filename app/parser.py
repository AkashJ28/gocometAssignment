"""Document parser module using PyMuPDF for text extraction and scan density fallback."""

from dataclasses import dataclass, field
import os
from typing import List, Literal, Optional
import pymupdf


def ocr_images(images: List[bytes]) -> Optional[str]:
    """Run OCR on image buffers using pytesseract if available."""
    try:
        import io
        from PIL import Image
        import pytesseract

        extracted = []
        for img_bytes in images:
            img = Image.open(io.BytesIO(img_bytes))
            text = pytesseract.image_to_string(img)
            if text and text.strip():
                extracted.append(text.strip())
        return "\n\n".join(extracted) if extracted else None
    except Exception:
        return None


@dataclass
class ParsedDocument:
    """Represents the parsed content and mode of an ingested document."""
    mime_type: str
    extraction_method: Literal["text_layer", "vision_default", "vision_fallback"]
    file_path: Optional[str] = None
    raw_text: Optional[str] = None
    ocr_text: Optional[str] = None
    grounding_source: Literal["text_layer", "ocr", "vision_unverified"] = "text_layer"
    page_images: List[bytes] = field(default_factory=list)
    page_count: int = 0


MAX_RENDER_PAGES = 10
DPI_RESOLUTION = 200
MIN_CHAR_DENSITY = 80
MIN_ALPHA_RATIO = 0.30


def _infer_mime_type(filename: str) -> str:
    """Infer mime type from filename extension."""
    ext = os.path.splitext(filename.lower())[1]
    if ext == ".pdf":
        return "application/pdf"
    if ext == ".png":
        return "image/png"
    if ext in (".jpg", ".jpeg"):
        return "image/jpeg"
    if ext == ".webp":
        return "image/webp"
    if ext == ".txt":
        return "text/plain"
    # Default fallback
    return "application/octet-stream"


def parse_document(
    file_bytes: bytes,
    filename: str,
    mime_type: Optional[str] = None,
    file_path: Optional[str] = None,
) -> ParsedDocument:
    """Parse document bytes using PyMuPDF and evaluate text layer vs scan density."""
    if not file_bytes:
        raise ValueError("Cannot parse empty file bytes.")

    resolved_mime = mime_type or _infer_mime_type(filename)

    # 1. Handle plain text documents
    if resolved_mime == "text/plain":
        return ParsedDocument(
            file_path=file_path,
            mime_type=resolved_mime,
            extraction_method="text_layer",
            grounding_source="text_layer",
            raw_text=file_bytes.decode("utf-8", errors="replace"),
            page_images=[],
            page_count=1,
        )

    # 2. Handle image formats directly
    if resolved_mime.startswith("image/"):
        ocr_res = ocr_images([file_bytes])
        return ParsedDocument(
            file_path=file_path,
            mime_type=resolved_mime,
            extraction_method="vision_default",
            grounding_source="ocr" if ocr_res else "vision_unverified",
            ocr_text=ocr_res,
            raw_text=ocr_res,
            page_images=[file_bytes],
            page_count=1,
        )

    # 3. Handle PDF formats
    if resolved_mime == "application/pdf":
        try:
            doc = pymupdf.open(stream=file_bytes, filetype="pdf")
        except Exception as e:
            raise ValueError(f"Failed to parse PDF document '{filename}': {e}") from e

        total_pages = len(doc)
        if total_pages == 0:
            doc.close()
            return ParsedDocument(
                file_path=file_path,
                mime_type=resolved_mime,
                extraction_method="vision_fallback",
                grounding_source="vision_unverified",
                raw_text=None,
                page_images=[],
                page_count=0,
            )

        pages_to_process = min(total_pages, MAX_RENDER_PAGES)
        extracted_pages_text: List[str] = []

        for i in range(pages_to_process):
            page = doc[i]
            page_text = page.get_text("text") or ""
            extracted_pages_text.append(page_text)

        joined_text = "\n\n".join(t.strip() for t in extracted_pages_text if t.strip())

        # Analyze character density across processed pages
        printable_non_whitespace = [c for c in joined_text if not c.isspace() and c.isprintable()]
        total_chars = len(printable_non_whitespace)
        alpha_chars = sum(1 for c in printable_non_whitespace if c.isalpha())
        alpha_ratio = (alpha_chars / total_chars) if total_chars > 0 else 0.0

        # Density Heuristic: Scanned or sparse PDF (< 80 chars OR < 30% alpha)
        if total_chars < MIN_CHAR_DENSITY or alpha_ratio < MIN_ALPHA_RATIO:
            # Escalation to vision fallback: rasterize pages to 200 DPI PNG buffers
            rendered_images: List[bytes] = []
            for i in range(pages_to_process):
                page = doc[i]
                pix = page.get_pixmap(dpi=DPI_RESOLUTION)
                rendered_images.append(pix.tobytes("png"))

            doc.close()
            ocr_res = ocr_images(rendered_images)
            return ParsedDocument(
                file_path=file_path,
                mime_type=resolved_mime,
                extraction_method="vision_fallback",
                grounding_source="ocr" if ocr_res else "vision_unverified",
                ocr_text=ocr_res,
                raw_text=ocr_res or (joined_text if joined_text else None),
                page_images=rendered_images,
                page_count=total_pages,
            )

        # High-density digital text layer detected
        doc.close()
        return ParsedDocument(
            file_path=file_path,
            mime_type=resolved_mime,
            extraction_method="text_layer",
            grounding_source="text_layer",
            raw_text=joined_text,
            page_images=[],
            page_count=total_pages,
        )

    # Unsupported format
    raise ValueError(f"Unsupported document mime type: {resolved_mime}")
