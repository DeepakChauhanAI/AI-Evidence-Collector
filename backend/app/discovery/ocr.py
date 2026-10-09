"""Read scanned PDFs — pages with no text layer — by rendering them and asking a vision model.

**Off by default, and that default is a data-egress decision, not a performance one.**
Enabling it (`DISCOVERY_VISION_OCR=true`) sends page images of your documents to the
configured LLM endpoint. Every other part of discovery stays local and deterministic;
this is the one place document contents leave the machine, so it never turns itself on.

Results are cached on disk keyed by the file's SHA-256, so re-scanning a folder does not
re-send the same pages.
"""
import hashlib
import io
import os

RENDER_SCALE = 2.0      # ~144 dpi — enough for the model to read a heading

_PROMPT = (
    "This is a page from a company document. Reply with plain text only: the document's "
    "title, then a one-sentence summary, then its main topics as comma-separated keywords. "
    "No preamble, no markdown."
)


def enabled():
    """Opt-in only. Returns True when the operator has explicitly accepted egress."""
    return os.getenv("DISCOVERY_VISION_OCR", "").strip().lower() in {"1", "true", "yes", "on"}


def read_scanned(path):
    """Text for a scanned PDF, or "" when vision is off, the LLM is unconfigured, or the
    render fails. Cached by content hash."""
    if not enabled():
        return ""
    from .. import llm
    if not llm.is_configured():
        return ""

    try:
        cached = _cache_path(path)
    except OSError:
        cached = ""
    if cached and os.path.exists(cached):
        try:
            with open(cached, encoding="utf-8") as f:
                return f.read()
        except OSError:
            pass                       # an unreadable cache is a miss, not a failure

    png = render_png(path)
    if not png:
        return ""
    try:
        text = llm.describe_image(png, _PROMPT).strip()
    except Exception:                  # a vision failure must not break a whole scan
        return ""
    if text and cached:
        _cache_write(cached, text)
    return text


def render_png(path, scale=RENDER_SCALE):
    """First page of the PDF as PNG bytes — a scanned policy puts its subject on page 1.
    Returns b"" when pypdfium2 or Pillow is unavailable, or the PDF will not open."""
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return b""
    try:
        doc = pdfium.PdfDocument(path)
        try:
            page = doc.get_page(0)
            try:
                bitmap = page.render(scale=scale)
                try:
                    buf = io.BytesIO()
                    bitmap.to_pil().save(buf, format="PNG")
                    return buf.getvalue()
                finally:
                    bitmap.close()
            finally:
                page.close()
        finally:
            doc.close()
    except Exception:                  # malformed PDF, or Pillow missing
        return b""


def _cache_dir():
    # Read per call, not at import, so tests can redirect it.
    return os.getenv("DISCOVERY_VISION_CACHE", "./.vision_cache")


def _cache_path(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return os.path.join(_cache_dir(), h.hexdigest() + ".txt")


def _cache_write(cached, text):
    """Best-effort: a cache write failure only costs a repeat call on the next scan."""
    try:
        os.makedirs(_cache_dir(), exist_ok=True)
        with open(cached, "w", encoding="utf-8") as f:
            f.write(text)
    except OSError:
        pass
