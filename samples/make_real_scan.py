"""Turn a clean PDF into a genuinely scanned-looking document (no text layer).

Rasterise at 150 DPI, rotate slightly, add noise and blur, JPEG-compress, and
re-wrap as an image-only PDF. Used to exercise the vision + OCR grounding path.
Usage: python samples/make_real_scan.py samples/clean_sample_invoice.pdf samples/real_scan_invoice
"""
import io
import random
import sys

import pymupdf
from PIL import Image, ImageFilter


def degrade(src_pdf: str, out_stem: str, seed: int = 7) -> None:
    random.seed(seed)
    doc = pymupdf.open(src_pdf)
    pix = doc[0].get_pixmap(dpi=150)
    img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("L")
    img = img.rotate(1.3, expand=True, fillcolor=235)
    px = img.load()
    w, h = img.size
    for _ in range(int(w * h * 0.01)):  # salt-and-pepper speckle
        px[random.randrange(w), random.randrange(h)] = random.choice((0, 255))
    img = img.filter(ImageFilter.GaussianBlur(0.8))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=35)
    buf.seek(0)
    Image.open(buf).save(f"{out_stem}.png")

    out = pymupdf.open()
    page = out.new_page(width=img.width * 72 / 150, height=img.height * 72 / 150)
    page.insert_image(page.rect, stream=buf.getvalue())
    out.save(f"{out_stem}.pdf")


if __name__ == "__main__":
    degrade(sys.argv[1], sys.argv[2])
