"""Rasterize FCC internal-photo PDFs into small, self-contained thumbnails.

FCC internal photos ship as a single multi-page PDF. To render them in a
dependency-free web gallery we rasterize each page to a downscaled JPEG and
embed it as a ``data:`` URI, so the shipped page makes zero external requests.

This is the ONE place the pipeline uses a non-stdlib library, and only at build
time: PyMuPDF (``pip install -e ".[build]"``). The generated ``web/`` artifact
never imports it. If it's missing, :func:`pdf_to_thumbnails` raises a clear hint.
"""

from __future__ import annotations

import base64
import io

_MISSING = (
    "PyMuPDF is required to rasterize FCC exhibit PDFs. Install the build extra:\n"
    '    pip install -e ".[build]"\n'
    "or run `build --no-photos` for a links-only index."
)


def _fitz():
    try:
        import fitz  # PyMuPDF
        return fitz
    except ImportError as e:  # pragma: no cover - env dependent
        raise RuntimeError(_MISSING) from e


def pdf_to_thumbnails(pdf_bytes: bytes, max_pages: int = 6, max_px: int = 900,
                      quality: int = 78) -> list[str]:
    """Return up to ``max_pages`` ``data:`` URIs, longest edge <= ``max_px``.

    Pages that are mostly a single photo (the usual case for internal-photo
    exhibits) render cleanly; text-heavy cover pages are included as-is.
    """
    fitz = _fitz()
    uris: list[str] = []
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        for page in doc:
            if len(uris) >= max_pages:
                break
            rect = page.rect
            longest = max(rect.width, rect.height) or 1
            scale = min(2.0, max_px / longest)
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            uris.append(_encode(pix, quality))
    finally:
        doc.close()
    return uris


def _encode(pix, quality: int) -> str:
    # Prefer JPEG via Pillow if available (smaller); else PNG straight from fitz.
    try:
        from PIL import Image
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        png = pix.tobytes("png")
        return "data:image/png;base64," + base64.b64encode(png).decode()
