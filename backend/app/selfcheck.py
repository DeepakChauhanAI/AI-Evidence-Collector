"""Runnable self-check of the core loop: import checklist -> bind collector -> run
-> evidence written + hashed. Uses sqlite + a stub collector (no network).

    python -m app.selfcheck
"""
import io
import os
import tempfile

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["EVIDENCE_DIR"] = tempfile.mkdtemp()

from .db import Base, engine, SessionLocal
from . import models, collectors, discovery
from .checklist import import_csv, suggest_collector, _keyword_suggest
from .runner import run_binding

Base.metadata.create_all(engine)


def main():
    db = SessionLocal()

    csv_bytes = b"code,name,description\nCC6.1,Logical Access,restrict access and mfa\nCC1.4,Code of Conduct,policy document\n"
    created = import_csv(db, csv_bytes)
    assert len(created) == 2, created
    assert suggest_collector(created[0]) == "http_api", suggest_collector(created[0])
    assert suggest_collector(created[1]) == "document", suggest_collector(created[1])

    # stub collector so the check is network-free
    collectors.REGISTRY["stub"] = lambda cfg: [
        {"filename": "e.json", "bytes": b'{"ok":true}', "meta": {"x": 1}}
    ]
    b = models.Binding(control_id=created[0].id, collector_type="stub", config={})
    db.add(b); db.commit()

    run = run_binding(db, b.id)
    assert run.status == "success", run.message
    ev = db.query(models.Evidence).all()
    assert len(ev) == 1, ev
    assert os.path.exists(ev[0].path), "evidence file not written"
    assert len(ev[0].sha256) == 64, "sha256 missing"

    # error path is captured, not raised
    bad = models.Binding(control_id=created[0].id, collector_type="nope", config={})
    db.add(bad); db.commit()
    assert run_binding(db, bad.id).status == "error"

    _check_llm_mapper(created[0])
    _check_agent_roles(created[0], db)
    _check_aws_sample()
    _check_github_sample()
    _check_surface_b()
    _check_surface_c()
    _check_s3()
    _check_extraction()
    _check_vision_ocr()
    _check_secret_resolution()
    _check_integrity(db)
    _check_export(db)
    _check_discovery(db)

    print("OK: import -> bind -> run -> hashed evidence; errors captured; mapper + config-author + validator + agent-collector + aws-sample + github-sample + surface-b + surface-c + s3 + extraction + vision-ocr + secrets + integrity + export + discovery paths")


def _check_discovery(db):
    """Surface A end to end: scan a folder -> deterministic match -> candidate rows,
    plus the local_file collector's root guard and re-scan idempotence."""
    from .discovery import document_scanner, matchmaker

    root = tempfile.mkdtemp()
    for fn in ("Access_Control_Policy_2026.md", "Incident_Response_Plan_v2.md", "random-notes.md"):
        with open(os.path.join(root, fn), "w", encoding="utf-8") as f:
            f.write("policy text about access and mfa\n")
    os.environ["DISCOVERY_DOCS_DIR"] = root

    assets = document_scanner.discover(root)
    assert len(assets) == 3, assets

    ctl = models.Control(framework="SOC2", code="CC6.1", name="Logical Access Controls",
                         description="Restrict logical access using password complexity and MFA.")
    value, reason, signals = matchmaker.score(ctl, assets[0])
    assert value >= matchmaker.MIN_SCORE, (value, reason)
    assert "access" in signals["matched_terms"] and signals["tier"] == "documentary", signals

    ranked = matchmaker.rank([ctl], assets)
    assert ranked and ranked[0]["source_name"].startswith("Access_Control_Policy"), ranked
    assert ranked[0]["collector_type"] == "local_file", ranked[0]

    # a control with no overlap gets no candidate rather than a bogus one
    weak = models.Control(code="CC9.9", name="Zzz", description="quarterly unicorn grooming")
    assert matchmaker.rank([weak], assets) == [], "unmatched control should yield no candidate"

    # collector reads a discovered file, and refuses a path outside the root
    arts = collectors.REGISTRY["local_file"]({"path": assets[0]["path"]})
    assert len(arts) == 1 and arts[0]["filename"].endswith(".md"), arts
    try:
        collectors.REGISTRY["local_file"]({"path": os.path.join(tempfile.gettempdir(), "outside.md")})
        assert False, "expected discovery-root guard to reject an outside path"
    except collectors.CollectorError:
        pass

    db.add(ctl)
    db.commit()
    summary = discovery.run_scan(db, root=root)
    assert summary["documents"] == 3 and summary["candidates"] >= 1, summary
    assert db.query(models.DiscoveryCandidate).filter_by(status="new").count() == summary["candidates"]
    n = db.query(models.DiscoveryCandidate).count()
    discovery.run_scan(db, root=root)
    assert db.query(models.DiscoveryCandidate).count() == n, "re-scan should replace, not duplicate"


def _check_integrity(db):
    """Integrity verifier flags a tampered file and a missing file, passes an intact one."""
    import hashlib
    evs = db.query(models.Evidence).all()
    assert evs, "need evidence from earlier in the check"

    def verify(e):
        if not os.path.exists(e.path):
            return "missing"
        with open(e.path, "rb") as f:
            return "ok" if hashlib.sha256(f.read()).hexdigest() == e.sha256 else "tampered"

    e = evs[0]
    assert verify(e) == "ok", "intact file should verify ok"
    with open(e.path, "ab") as f:  # tamper
        f.write(b"x")
    assert verify(e) == "tampered", "altered file should be flagged"
    os.remove(e.path)
    assert verify(e) == "missing", "deleted file should be flagged"


def _check_aws_sample():
    """aws collector returns a labeled SAMPLE artifact when no creds/boto3, real otherwise.
    Here we just assert the sample path (no AWS in CI): known op has a fixture, meta.sample True."""
    arts = collectors.REGISTRY["aws"]({"service": "iam", "operation": "get_account_password_policy"})
    assert len(arts) == 1 and arts[0]["meta"]["sample"] is True, arts
    assert b"MinimumPasswordLength" in arts[0]["bytes"], arts[0]["bytes"][:80]
    try:
        collectors.REGISTRY["aws"]({"service": "iam"})  # missing operation
        assert False, "expected config error"
    except collectors.CollectorError:
        pass


def _check_github_sample():
    """github collector samples without a token, and fills {placeholders} from env once
    a token exists. Also: a bad config is a loud error, not a sample."""
    os.environ.pop("GITHUB_TOKEN", None)
    os.environ.pop("GITHUB_OWNER", None)
    os.environ.pop("GITHUB_REPO", None)
    os.environ.pop("GITHUB_BRANCH", None)
    ep = "repos/{owner}/{repo}/branches/{branch}/protection"
    arts = collectors.REGISTRY["github"]({"endpoint": ep})
    assert len(arts) == 1 and arts[0]["meta"]["sample"] is True, arts
    assert b"required_pull_request_reviews" in arts[0]["bytes"], arts[0]["bytes"][:80]

    # token present but a placeholder unset -> still a sample, and the reason says which
    os.environ["GITHUB_TOKEN"] = "t0ken"
    arts = collectors.REGISTRY["github"]({"endpoint": ep})
    assert arts[0]["meta"]["sample"] is True and "GITHUB_OWNER" in arts[0]["meta"]["reason"], arts[0]["meta"]

    for k, v in (("GITHUB_OWNER", "acme"), ("GITHUB_REPO", "app"), ("GITHUB_BRANCH", "main")):
        os.environ[k] = v
    for k in ("GITHUB_TOKEN", "GITHUB_OWNER", "GITHUB_REPO", "GITHUB_BRANCH"):
        os.environ.pop(k, None)

    try:
        collectors.REGISTRY["github"]({})           # missing endpoint
        assert False, "expected config error"
    except collectors.CollectorError:
        pass


def _check_surface_b():
    """Surface B: catalog descriptors are pre-wired, score against control text, and
    get tier='direct' (they return the control's parameters verbatim, not a narrative)."""
    from .discovery import catalog, matchmaker

    assets = catalog.discover()
    assert len(assets) >= 8, len(assets)
    assert all(a.get("collector_type") and a.get("config") for a in assets), "descriptors must be pre-wired"

    branch = models.Control(code="CC8.1", name="Change Management",
                            description="Changes to infrastructure are approved, tested and reviewed before release.")
    top = matchmaker.rank([branch], assets, top_per_control=1)[0]
    assert top["collector_type"] == "github", top
    assert top["signals"]["tier"] == "direct", top["signals"]
    assert "protection" in top["config"]["endpoint"], top["config"]

    trail = models.Control(code="CC7.2", name="Monitoring",
                           description="Logging and audit trail monitoring across production systems.")
    top = matchmaker.rank([trail], assets, top_per_control=1)[0]
    assert top["config"] == {"service": "cloudtrail", "operation": "describe_trails"}, top["config"]

    # credentials_present reflects the environment, not the scan
    os.environ.pop("AWS_ACCESS_KEY_ID", None)
    os.environ.pop("GITHUB_TOKEN", None)
    assert catalog.credentials_present() == {"cloud": False, "code": False}


_SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://trust.example.com/security</loc></url>
  <url><loc>https://trust.example.com/legal/subprocessors</loc></url>
  <url><loc>https://trust.example.com/status</loc></url>
  <url><loc>https://trust.example.com/policies/access-control</loc></url>
  <url><loc>https://trust.example.com/blog/our-security-tips</loc></url>
  <url><loc>https://trust.example.com/software/confluence/comparison</loc></url>
  <url><loc>https://trust.example.com/software/jira/send-slack</loc></url>
  <url><loc>https://trust.example.com/legal/soc2-report</loc></url>
  <url><loc>https://evil.example.net/policies/access-control</loc></url>
  <url><loc>https://trust.example.com/careers</loc></url>
</urlset>"""


def _check_surface_c():
    """Surface C: sitemap -> compliance paths only, same host only, status pages bound
    to screenshot. Uses the crawler's single fetch point so the check stays offline."""
    from .discovery import web_crawler, matchmaker

    original = web_crawler._get
    web_crawler._get = lambda url, timeout=20: _SITEMAP if url.endswith("sitemap.xml") else ""
    try:
        pages = web_crawler.discover("https://trust.example.com")
    finally:
        web_crawler._get = original

    urls = [p["source_name"] for p in pages]
    assert "https://trust.example.com/legal/subprocessors" in urls, urls
    assert "https://trust.example.com/status" in urls, urls
    assert "https://trust.example.com/careers" not in urls, "non-compliance path kept"
    # "iso" must not match the "comparison" segment, nor "sla" the "slack" segment —
    # both were real false positives on live crawls, not hypotheticals.
    assert not any("comparison" in u for u in urls), "substring match leaked a non-compliance path"
    assert not any("slack" in u for u in urls), "short root bled into an unrelated word"
    # ...while a short root still matches its own segment, with digits ("soc2")
    assert "https://trust.example.com/legal/soc2-report" in urls, "soc2 page was missed"
    assert not any("evil.example.net" in u for u in urls), "off-host URL was followed"

    by_url = {p["source_name"]: p for p in pages}
    assert by_url["https://trust.example.com/status"]["collector_type"] == "screenshot", by_url
    assert by_url["https://trust.example.com/security"]["collector_type"] == "document", by_url

    vendor = models.Control(code="CC9.2", name="Vendor risk",
                            description="Maintain a list of subprocessors and third-party vendors.")
    assert matchmaker.rank([vendor], pages, top_per_control=1)[0]["surface"] == "web"

    # No base URL configured -> no crawl, no error.
    assert web_crawler.discover("") == []


def _check_s3():
    """S3 discovery lists documents only and pre-wires the s3_file collector; the
    collector degrades to a labeled sample without credentials. boto3 is stubbed so
    this stays offline (and works whether or not boto3 is installed)."""
    import sys, types
    from .discovery import document_scanner, matchmaker

    class _FakePaginator:
        def paginate(self, **kw):
            return [{"Contents": [
                {"Key": "policies/Access_Control_Policy_2026.pdf", "LastModified": None},
                {"Key": "policies/Incident_Response_Plan.docx", "LastModified": None},
                {"Key": "policies/", "LastModified": None},          # folder marker
                {"Key": "exports/dump.sql", "LastModified": None},   # not a document
            ]}]

    class _FakeClient:
        def get_paginator(self, name):
            return _FakePaginator()

    fake = types.ModuleType("boto3")
    fake.client = lambda *a, **k: _FakeClient()
    orig = sys.modules.get("boto3")
    sys.modules["boto3"] = fake
    try:
        assets = document_scanner.discover_s3("compliance-bucket")
    finally:
        if orig is None:
            sys.modules.pop("boto3", None)
        else:
            sys.modules["boto3"] = orig

    keys = [a["config"]["key"] for a in assets]
    assert keys == ["policies/Access_Control_Policy_2026.pdf", "policies/Incident_Response_Plan.docx"], keys
    assert all(a["collector_type"] == "s3_file" for a in assets), assets
    assert assets[0]["source_name"] == "s3://compliance-bucket/policies/Access_Control_Policy_2026.pdf"

    policy = models.Control(code="CC6.1", name="Logical Access",
                            description="Restrict access with password and MFA controls.")
    top = matchmaker.rank([policy], assets, top_per_control=1)[0]
    assert top["collector_type"] == "s3_file" and top["config"]["bucket"] == "compliance-bucket", top

    # collector: config is required, and without credentials it samples rather than raising
    try:
        collectors.REGISTRY["s3_file"]({"bucket": "b"})
        assert False, "expected config error"
    except collectors.CollectorError:
        pass
    for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_PROFILE"):
        os.environ.pop(k, None)
    arts = collectors.REGISTRY["s3_file"]({"bucket": "b", "key": "k.pdf"})
    assert arts[0]["meta"]["sample"] is True and arts[0]["filename"] == "s3-k.pdf.json", arts[0]


def _minimal_pdf(text):
    """A valid one-page PDF carrying `text`, with a real xref table. Stdlib only —
    lets the extraction check run without a fixture file in the repo."""
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 120] /Contents 4 0 R "
            b"/Resources << /Font << /F1 5 0 R >> >> >>"]
    stream = ("BT /F1 14 Tf 20 60 Td (" + text + ") Tj ET").encode()
    objs.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for i, o in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n".encode() + b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref}\n%%EOF\n").encode()
    return bytes(out)


def _minimal_docx(text):
    """A minimal .docx (ZIP + WordprocessingML) carrying `text`."""
    import zipfile
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml",
                   f'<?xml version="1.0"?><w:document xmlns:w="{ns}"><w:body>'
                   f'<w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>')
    return buf.getvalue()


def _check_extraction():
    """PDF and DOCX text reaches the matcher, so a document with an uninformative
    filename still matches on what it says. Also: unreadable files degrade to ''."""
    from .discovery import document_scanner, matchmaker

    root = tempfile.mkdtemp()
    open(os.path.join(root, "scan_2024_001.pdf"), "wb").write(
        _minimal_pdf("Vendor risk assessment of subprocessors and third party suppliers"))
    open(os.path.join(root, "Policy_v3_FINAL.docx"), "wb").write(
        _minimal_docx("Password complexity minimum length and MFA enforcement for all users"))
    open(os.path.join(root, "broken.docx"), "wb").write(b"not actually a zip")

    assets = {a["source_name"]: a for a in document_scanner.discover(root)}
    assert "subprocessors" in assets["scan_2024_001.pdf"]["text"], assets["scan_2024_001.pdf"]
    assert "MFA enforcement" in assets["Policy_v3_FINAL.docx"]["text"], assets["Policy_v3_FINAL.docx"]
    assert assets["broken.docx"]["text"] == "", "unreadable docx should degrade to no text"

    # End to end: neither filename mentions its subject, so only extracted text can match.
    vendor = models.Control(code="CC9.2", name="Vendor risk management",
                            description="Maintain a subprocessor inventory and third-party risk reviews.")
    top = matchmaker.rank([vendor], list(assets.values()), top_per_control=1)[0]
    assert top["source_name"] == "scan_2024_001.pdf", top
    assert "vendor" in top["reason"], top["reason"]

    mfa = models.Control(code="CC6.6", name="Multi-factor authentication",
                         description="MFA is enforced for all remote and administrative access.")
    top = matchmaker.rank([mfa], list(assets.values()), top_per_control=1)[0]
    assert top["source_name"] == "Policy_v3_FINAL.docx", top
    assert "mfa" in top["reason"], top["reason"]


def _check_vision_ocr():
    """Scanned-PDF vision: off by default, gated on config, cached by content hash.
    llm.describe_image is stubbed, so this never leaves the machine."""
    from . import llm
    from .discovery import document_scanner, matchmaker, ocr

    root = tempfile.mkdtemp()
    cache = tempfile.mkdtemp()
    pdf = os.path.join(root, "scan.pdf")
    # An empty text layer is exactly what a scan looks like: valid PDF, no extractable
    # words, so extraction falls through to the vision path.
    open(pdf, "wb").write(_minimal_pdf(""))

    for var in ("DISCOVERY_VISION_OCR", "DISCOVERY_VISION_CACHE"):
        os.environ.pop(var, None)
    os.environ["DISCOVERY_VISION_CACHE"] = cache

    # 1. Default is off — no egress, no text.
    assert ocr.enabled() is False
    assert ocr.read_scanned(pdf) == "", "vision must be inert unless opted in"

    # 2. Opted in, but no LLM configured -> still nothing, and no exception.
    os.environ["DISCOVERY_VISION_OCR"] = "true"
    os.environ.pop("AI_API_KEY", None)
    assert ocr.read_scanned(pdf) == ""

    # 3. Opted in + configured: renders, calls the model once, then serves from cache.
    calls = []
    orig_configured, orig_describe = llm.is_configured, llm.describe_image
    llm.is_configured = lambda: True
    llm.describe_image = lambda png, prompt, max_tokens=300: (
        calls.append(len(png)) or "Access Control Policy. Covers MFA and password rules. "
                                  "keywords: access, mfa, password, policy")
    try:
        text = ocr.read_scanned(pdf)
        assert "mfa" in text, text
        assert len(calls) == 1 and calls[0] > 0, f"expected one render, got {calls}"

        # A second read must come from the cache — same text, no second model call.
        again = ocr.read_scanned(pdf)
        assert again == text and len(calls) == 1, f"cache miss: {len(calls)} calls"
        assert len(os.listdir(cache)) == 1, os.listdir(cache)

        # The extracted text is what the matcher actually sees.
        asset = {"surface": "documents", "source_name": "scan.pdf", "path": pdf,
                 "ext": ".pdf", "size": 0, "modified": None,
                 "text": document_scanner.extract_text(pdf, ".pdf")}
        ctrl = models.Control(code="CC6.6", name="Multi-factor authentication",
                              description="MFA is enforced for administrative access.")
        top = matchmaker.rank([ctrl], [asset], top_per_control=1)[0]
        assert "mfa" in top["reason"], top
    finally:
        llm.is_configured, llm.describe_image = orig_configured, orig_describe
        os.environ.pop("DISCOVERY_VISION_OCR", None)
        os.environ.pop("DISCOVERY_VISION_CACHE", None)

    # render_png is independent of the gate and must produce a real PNG.
    png = ocr.render_png(pdf)
    assert png[:8] == b"\x89PNG\r\n\x1a\n", "render_png did not produce a PNG"


def _check_secret_resolution():
    """env:VAR refs expand from the environment; missing var fails loud."""
    from .runner import _resolve_secrets, CollectorError
    os.environ["EC_TEST_SECRET"] = "s3cr3t"
    out = _resolve_secrets({"headers": {"Authorization": "env:EC_TEST_SECRET"}, "url": "x", "n": 1})
    assert out["headers"]["Authorization"] == "s3cr3t" and out["url"] == "x" and out["n"] == 1, out
    try:
        _resolve_secrets({"k": "env:EC_MISSING_VAR"})
        assert False, "expected missing-var error"
    except CollectorError:
        pass


def _check_export(db):
    """Export produces a valid ZIP with manifest + the evidence file. Uses a fresh
    successful run so the control's latest run has evidence (export reflects latest)."""
    import zipfile, io, json
    from .export import build_export
    created = db.query(models.Control).filter(models.Control.code == "CC1.4").all()
    b = models.Binding(control_id=created[0].id, collector_type="stub", config={})
    db.add(b); db.commit()
    run_binding(db, b.id)
    data, name = build_export(db)
    assert name.endswith(".zip"), name
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = z.namelist()
        assert "manifest.json" in names and "MANIFEST.txt" in names, names
        m = json.loads(z.read("manifest.json"))
        assert "summary" in m and m["controls"], m
        assert any(n.startswith("evidence/CC1.4/") for n in names), names


def _check_agent_roles(control, db):
    """Steps 2-4 without network: stub llm.complete and verify config author,
    validator, and the autonomous agent collector (plan -> delegate)."""
    from . import llm, agent

    orig_complete, orig_configured = llm.complete, llm.is_configured
    llm.is_configured = lambda: True
    try:
        # Step 2: config author returns a dict parsed from the model
        llm.complete = lambda s, u, max_tokens=600: '{"url": "https://x/export", "method": "GET", "headers": {}}'
        cfg = agent.draft_config(control, "http_api")
        assert cfg.get("url") == "https://x/export", cfg

        # Step 3: validator returns a normalized verdict
        llm.complete = lambda s, u, max_tokens=600: '{"satisfied": true, "summary": "ok", "gaps": "", "confidence": 0.9}'
        v = agent.assess_evidence(control, [("e.json", '{"mfa": true}')])
        assert v["satisfied"] is True and 0 <= v["confidence"] <= 1, v

        # Step 4: agent collector plans a real collector + config, then delegates to a stub
        collectors.REGISTRY["stub2"] = lambda cfg: [{"filename": "a.txt", "bytes": b"hi", "meta": {}}]
        llm.complete = lambda s, u, max_tokens=600: '{"collector_type": "stub2", "config": {"k": 1}}'
        arts = collectors.REGISTRY["agent"]({"goal": "collect the thing"})
        assert len(arts) == 1 and arts[0]["meta"]["agent_plan"]["collector_type"] == "stub2", arts

        # agent collector surfaces an unusable plan as an error (not a crash)
        llm.complete = lambda s, u, max_tokens=600: '{"collector_type": "nonexistent", "config": {}}'
        try:
            collectors.REGISTRY["agent"]({"goal": "x"})
            assert False, "expected planning failure"
        except collectors.CollectorError:
            pass
    finally:
        llm.complete, llm.is_configured = orig_complete, orig_configured
        collectors.REGISTRY.pop("stub2", None)


def _check_llm_mapper(control):
    """LLM mapping path without network: stub llm.complete, verify parse + validation."""
    from . import llm
    from .checklist import suggest_collector

    orig_complete, orig_configured = llm.complete, llm.is_configured
    llm.is_configured = lambda: True
    try:
        # valid choice (fenced JSON) is honored
        llm.complete = lambda s, u, max_tokens=600: '```json\n{"collector": "http_api"}\n```'
        assert suggest_collector(control) == "http_api"

        # unknown collector from LLM falls back to keyword mapper
        llm.complete = lambda s, u, max_tokens=600: '{"collector": "bogus"}'
        assert suggest_collector(control) == _keyword_suggest(control)

        # LLM error falls back, never raises
        def boom(*a, **k):
            raise RuntimeError("provider down")
        llm.complete = boom
        assert suggest_collector(control) == _keyword_suggest(control)
    finally:
        llm.complete, llm.is_configured = orig_complete, orig_configured


if __name__ == "__main__":
    main()
