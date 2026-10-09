"""Surface C: web, portal and internal wiki discovery.

Given a base URL, finds same-site pages that look like compliance evidence — from
`sitemap.xml` when the site has one, otherwise from the links on the base page. Each
survivor becomes a candidate bound to the existing `document` collector (or `screenshot`
for a live status dashboard). Nothing new is fetched at collection time; discovery only
produces the URL that `document`/`screenshot` would already have taken.

ponytail: matches on the URL **path**, not page text. Path tokens ("/subprocessors",
"/policies/access-control") carry the signal, and fetching every page to read its title
is N requests for marginal gain. Add page-text extraction when path matching measurably misses.
"""
import re
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlparse

import requests

# Path words that make a page worth considering as evidence. "policy" covers
# policies/policy; "processor" covers sub-processors (hyphens split segments).
COMPLIANCE_PATHS = [
    "security", "privacy", "compliance", "soc", "iso", "policy", "subprocessor",
    "processor", "trust", "legal", "terms", "dpa", "sla", "status", "gdpr",
    "hipaa", "data-protection", "vendor", "third-party", "availability", "accessib",
]

# A live dashboard has no document to download — capture the rendered page instead.
_SCREENSHOT_PATHS = ["status", "dashboard", "monitor"]

_UA = {"User-Agent": "PanaceaEvidenceCollector/1.0 (+compliance evidence discovery)"}


def discover(base_url, max_pages=50, timeout=20):
    """Asset dicts for compliance-looking pages on `base_url`'s host, capped at max_pages."""
    base = (base_url or "").strip().rstrip("/")
    if not base:
        return []
    host = urlparse(base).netloc

    urls = _from_sitemap(base, host, timeout) or _from_links(base, host, timeout)
    seen, out = set(), []
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        path = urlparse(url).path
        if not _is_compliance(path):
            continue
        out.append(_asset(url, path))
        if len(out) >= max_pages:
            break
    return out


def _get(url, timeout=20):
    """Single fetch point — monkeypatched in the self-check so tests stay offline."""
    try:
        resp = requests.get(url, headers=_UA, timeout=timeout)
        if resp.status_code != 200:
            return ""
        return resp.text
    except requests.RequestException:
        return ""


def _locs(xml_text):
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None, []
    return root, [e.text.strip() for e in root.iter() if e.tag.endswith("loc") and e.text]


def _from_sitemap(base, host, timeout):
    root, locs = _locs(_get(f"{base}/sitemap.xml", timeout))
    if root is None:
        return []
    if not root.tag.endswith("sitemapindex"):
        return [u for u in locs if _same_host(u, host)]
    pages = []
    for child in locs[:5]:  # ponytail: cap child sitemaps; revisit if a site nests deeper
        _, child_locs = _locs(_get(child, timeout))
        pages += child_locs
    return [u for u in pages if _same_host(u, host)]


def _from_links(base, host, timeout):
    """No sitemap: take the base page's own links (depth 1). Deeper crawling is a
    later rung — one page's link list already covers most trust centres and wikis."""
    html = _get(base, timeout)
    hrefs = re.findall(r'href=["\']([^"\'#]+)["\']', html, flags=re.I)
    return [urljoin(base + "/", h) for h in hrefs if _same_host(urljoin(base + "/", h), host)]


def _same_host(url, host):
    """Only follow links on the configured host. Discovery output becomes a stored URL
    that a collector later fetches, so a sitemap must not be able to point it elsewhere."""
    return urlparse(url).netloc in ("", host)


def _segments(path):
    return [s for s in re.split(r"[^a-z0-9]+", path.lower()) if s]


def _matches(path, words):
    """Match whole path segments, never substrings, and never let a short root bleed
    into an unrelated word.

    Two false positives this rules out, both found on live crawls rather than in tests:
      • as a substring, "iso" hits "com-parISO-n" and "soc" hits "asSOCiation";
      • as a prefix, "sla" hits "SLAck" and "soc" hits "socket".
    Short roots (<= 3 chars: iso, soc, sla, dpa) must therefore equal a whole segment,
    optionally followed by digits ("soc" still matches "soc2", "iso" matches "iso27001").
    Longer roots keep prefix matching, which is what carries inflections
    ("policy" -> "policies", "security" -> "cybersecurity" is intentionally not matched).
    """
    segments = _segments(path)
    for w in words:
        for seg in segments:
            if len(w) <= 3:
                if seg == w or re.fullmatch(w + r"\d*", seg):
                    return True
            elif seg.startswith(w):
                return True
    return False


def _is_compliance(path):
    return _matches(path, COMPLIANCE_PATHS)


def _asset(url, path):
    words = re.sub(r"[^a-z0-9]+", " ", path.lower())
    collector = "screenshot" if _matches(path, _SCREENSHOT_PATHS) else "document"
    return {
        "surface": "web",
        "source_name": url,
        "collector_type": collector,
        "config": {"url": url},
        "text": words,
    }
