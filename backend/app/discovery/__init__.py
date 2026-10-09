"""Autonomous evidence discovery: find candidate artifacts for each control, without
a human pasting URLs. A scan produces *staging* candidates (DiscoveryCandidate rows);
confirming one promotes it to an ordinary Binding, so the run/hash/validate path is
untouched. See DISCOVERY_PLAN.md.

Surface A (local documents) is implemented; S3, cloud/code catalogs, and the web
crawler are the next rungs and slot in behind `document_scanner` / `matchmaker`.
"""
import os

from . import catalog, web_crawler
from .document_scanner import discover, discover_s3
from .matchmaker import rank

DEFAULT_ROOT = "./compliance_docs"


def run_scan(db, root=None):
    """Scan configured surfaces and refresh the *unresolved* candidates.
    Bound/dismissed candidates are kept (audit trail); only status='new' rows are
    replaced, so re-scanning never discards an auditor's decision."""
    from ..models import Control, DiscoveryCandidate

    root = os.path.abspath(root or os.getenv("DISCOVERY_DOCS_DIR", DEFAULT_ROOT))
    web_base = os.getenv("DISCOVERY_WEB_URL", "").strip()
    bucket = os.getenv("DISCOVERY_S3_BUCKET", "").strip()

    documents = discover(root)
    if bucket:
        documents += discover_s3(bucket, prefix=os.getenv("DISCOVERY_S3_PREFIX", ""),
                                 region=os.getenv("AWS_REGION") or None)
    descriptors = catalog.discover()              # Surface B: static, no crawl
    pages = web_crawler.discover(web_base) if web_base else []   # Surface C: only when configured
    controls = db.query(Control).all()
    candidates = rank(controls, documents + descriptors + pages)

    db.query(DiscoveryCandidate).filter(DiscoveryCandidate.status == "new").delete()
    for c in candidates:
        db.add(DiscoveryCandidate(**c))
    db.commit()
    return {"root": root, "web_url": web_base or None, "s3_bucket": bucket or None,
            "documents": len(documents), "descriptors": len(descriptors), "pages": len(pages),
            "controls": len(controls), "candidates": len(candidates)}
