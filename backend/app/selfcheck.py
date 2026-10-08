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
from . import models, collectors
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
    _check_secret_resolution()
    _check_integrity(db)
    _check_export(db)

    print("OK: import -> bind -> run -> hashed evidence; errors captured; mapper + config-author + validator + agent-collector + aws-sample + secrets + integrity + export paths")


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
