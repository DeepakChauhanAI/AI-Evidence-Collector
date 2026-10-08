"""Executes a binding's collector, writes artifacts to the blob store, records
Run + Evidence rows, then runs the AI validator over the result. This is the heart
of the loop — everything else is CRUD."""
import os
import hashlib
from datetime import datetime
from .models import Binding, Run, Evidence
from .collectors import get_collector, CollectorError
from . import agent

EVIDENCE_DIR = os.getenv("EVIDENCE_DIR", "./evidence_store")


def _resolve_secrets(cfg):
    """Expand "env:VAR" string values to os.environ[VAR] so secrets stay out of the DB.
    The config stores the reference ("env:AWS_SECRET"); the real value lives in the
    process environment. Walks dicts/lists. Missing var -> CollectorError (fail loud)."""
    if isinstance(cfg, dict):
        return {k: _resolve_secrets(v) for k, v in cfg.items()}
    if isinstance(cfg, list):
        return [_resolve_secrets(v) for v in cfg]
    if isinstance(cfg, str) and cfg.startswith("env:"):
        var = cfg[4:]
        val = os.getenv(var)
        if val is None:
            raise CollectorError(f"config references env:{var} but it is not set")
        return val
    return cfg


def _as_text(data, filename):
    """Decode evidence for the validator; note binaries instead of decoding."""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return f"(binary file {filename}, {len(data)} bytes — content not shown)"


def run_binding(db, binding_id):
    binding = db.get(Binding, binding_id)
    if not binding:
        raise CollectorError(f"binding {binding_id} not found")

    run = Run(binding_id=binding.id, status="pending")
    db.add(run)
    db.commit()

    try:
        collector = get_collector(binding.collector_type)
        artifacts = collector(_resolve_secrets(binding.config or {}))
        day_dir = os.path.join(EVIDENCE_DIR, datetime.utcnow().strftime("%Y-%m-%d"), f"run{run.id}")
        os.makedirs(day_dir, exist_ok=True)
        texts = []
        for art in artifacts:
            data = art["bytes"]
            sha = hashlib.sha256(data).hexdigest()
            path = os.path.join(day_dir, art["filename"])
            with open(path, "wb") as f:
                f.write(data)
            db.add(Evidence(run_id=run.id, filename=art["filename"], path=path,
                            sha256=sha, meta=art.get("meta") or {}))
            texts.append((art["filename"], _as_text(data, art["filename"])))
        run.status = "success"
        run.message = f"{len(artifacts)} artifact(s)"
        # Validator/summarizer: judge the evidence against the control (no-op if LLM off).
        run.assessment = agent.assess_evidence(binding.control, texts)
    except Exception as e:  # collectors hit external systems; capture failure as audit record
        run.status = "error"
        run.message = str(e)
    db.commit()
    if run.status == "error":
        _alert(binding, run)
    return run


def _alert(binding, run):
    """Best-effort failure notification. POSTs to ALERT_WEBHOOK (Slack-compatible) if
    set; otherwise logs. A failed alert must never break the run itself."""
    code = binding.control.code if binding.control else "?"
    text = f"Evidence collection FAILED — {code} / {binding.collector_type} (run {run.id}): {run.message}"
    url = os.getenv("ALERT_WEBHOOK", "").strip()
    if not url:
        print(f"[ALERT] {text}")
        return
    try:
        import requests
        requests.post(url, json={"text": text}, timeout=10)
    except Exception as e:
        print(f"[ALERT] webhook failed ({e}); original: {text}")
