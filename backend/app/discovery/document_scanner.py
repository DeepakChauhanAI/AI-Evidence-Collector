"""Surface A: discover documents in the local compliance folder.

Returns plain metadata assets — discovery never collects; the `local_file` collector
does that once a candidate is confirmed:
    {surface, source_name, path, ext, size, modified, text}

Text extraction feeds the matcher's `text` signal, so a document called `scan_2024.pdf`
can still match on what it says. It is best-effort and never fatal: anything unreadable
falls back to filename matching, which is how discovery worked before extraction existed.
"""
import os
import re
import zipfile
from xml.etree import ElementTree as ET

DOC_EXTS = {".pdf", ".docx", ".doc", ".md", ".txt", ".csv", ".rtf", ".xlsx", ".xls", ".pptx"}
_PLAIN_EXTS = {".md", ".txt", ".csv"}         # stdlib, no dependency
_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build"}

MAX_TEXT = 20000        # chars of document text kept; enough to match on, cheap to hold
MAX_PDF_PAGES = 25      # a policy's first pages carry its subject; reading 300 is waste


def extract_text(path, ext):
    """Best-effort text for match signals. Returns "" when nothing can be read.

    .md/.txt/.csv — stdlib. .docx — a ZIP of XML, also stdlib (no dependency at all).
    .pdf — pypdfium2, optional: without it PDFs match on filename as they did before.
    A PDF with no text layer is a scan; that goes to vision OCR, which is off unless
    the operator has explicitly opted into sending documents to the LLM endpoint.
    """
    if ext in _PLAIN_EXTS:
        return _head(path)
    if ext == ".docx":
        return _docx_text(path)
    if ext == ".pdf":
        text = _pdf_text(path)
        if text:
            return text
        from . import ocr                 # local import: ocr reaches out to the LLM module
        return ocr.read_scanned(path)
    return ""


def _docx_text(path):
    """A .docx is a ZIP; the words are <w:t> runs inside word/document.xml.

    Matching the full WordprocessingML namespace rather than a tag suffix keeps
    unrelated tags (<w:tab>, <w:tbl>) from being read as text.
    """
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml")
        root = ET.fromstring(xml)
    except (OSError, KeyError, zipfile.BadZipFile, ET.ParseError):
        return ""
    return " ".join(t.text for t in root.iter(ns + "t") if t.text)[:MAX_TEXT]


def _pdf_text(path):
    """The PDF's text layer via pypdfium2. Empty for a scan (no text layer) or a
    malformed file, or when the optional library is absent.

    ponytail: handles are closed on the happy path only — on a parse error they are
    left to the GC rather than wrapped in nested finally blocks. pdfium is process-scoped
    and a failed parse is a one-off, not a leak that accumulates.
    """
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return ""
    parts = []
    try:
        doc = pdfium.PdfDocument(path)
        for i in range(min(len(doc), MAX_PDF_PAGES)):
            page = doc.get_page(i)
            textpage = page.get_textpage()
            parts.append(textpage.get_text_range())
            textpage.close()
            page.close()
        doc.close()
    except Exception:          # pdfium raises its own error types for malformed PDFs
        return ""
    return " ".join(" ".join(parts).split())[:MAX_TEXT]


def discover(root, max_files=1000):
    """Walk `root`, returning one asset per document file (capped at max_files).

    ponytail: text is extracted inline, so a scan is IO-bound on the folder — roughly
    proportional to total document pages, capped by MAX_PDF_PAGES each. Fine for a
    compliance folder (hundreds of files); if a corpus ever reaches tens of thousands,
    cache extraction by path+mtime instead of re-reading every scan.
    """
    root = os.path.abspath(root)
    if not os.path.isdir(root):
        return []
    assets = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
        for name in filenames:
            ext = os.path.splitext(name)[1].lower()
            if ext not in DOC_EXTS:
                continue
            full = os.path.join(dirpath, name)
            try:
                st = os.stat(full)
            except OSError:                      # raced away / permission denied
                continue
            assets.append({
                "surface": "documents",
                "source_name": os.path.relpath(full, root).replace("\\", "/"),
                "path": full,
                "ext": ext,
                "size": st.st_size,
                "modified": st.st_mtime,
                "text": extract_text(full, ext),
            })
            if len(assets) >= max_files:
                return assets
    return assets


def discover_s3(bucket, prefix="", region=None, max_keys=500):
    """List document objects in an S3 bucket (Surface A's remote half).

    Returns assets pre-wired with the `s3_file` collector rather than `local_file`,
    so confirming one fetches the object rather than reading a local path. Without
    boto3/credentials this returns [] — an unreadable bucket is not a scan failure.
    """
    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError:
        return []

    try:
        client = boto3.client("s3", region_name=region)
        pages = client.get_paginator("list_objects_v2").paginate(
            Bucket=bucket, Prefix=prefix, PaginationConfig={"MaxItems": max_keys})
        objects = [o for page in pages for o in page.get("Contents", [])]
    except (BotoCoreError, ClientError):
        return []

    assets = []
    for obj in objects:
        key = obj["Key"]
        ext = os.path.splitext(key)[1].lower()
        if ext not in DOC_EXTS:                 # folders and non-documents are not evidence
            continue
        assets.append({
            "surface": "documents",
            "source_name": f"s3://{bucket}/{key}",
            "collector_type": "s3_file",
            "config": {"bucket": bucket, "key": key, "region": region},
            "text": re.sub(r"[^a-z0-9]+", " ", key.lower()),
            "ext": ext,
            "modified": obj["LastModified"].timestamp() if obj.get("LastModified") else None,
        })
    return assets


def _head(path, limit=2000):
    """First `limit` chars of a text file, for match signals. Failures degrade to ''."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read(limit)
    except OSError:
        return ""
