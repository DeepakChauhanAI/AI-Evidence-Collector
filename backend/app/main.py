"""FastAPI app: checklist import, controls, bindings (map collectors), runs, evidence.
Thin CRUD over the models + the run/schedule machinery."""
import os
from datetime import datetime
from fastapi import FastAPI, Depends, UploadFile, File, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .db import Base, engine, get_db
from . import models, scheduler
from .checklist import import_csv, suggest_collector, _keyword_suggest
from .runner import run_binding
from .collectors import REGISTRY
from .soc2_starter import seed_controls
from . import agent
from .export import build_export


def require_auth(request: Request):
    """Shared-token auth. Off when API_TOKEN unset (local dev). Token via
    'Authorization: Bearer <t>' or '?token=<t>' (the latter so <a href> downloads work)."""
    expected = os.getenv("API_TOKEN", "").strip()
    if not expected:
        return
    header = request.headers.get("authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else request.query_params.get("token", "")
    if token != expected:
        raise HTTPException(401, "invalid or missing API token")


Base.metadata.create_all(engine)
app = FastAPI(title="Evidence Collection Agent", dependencies=[Depends(require_auth)])
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def _startup():
    scheduler.start()


# ---- schemas ----
class BindingIn(BaseModel):
    control_id: int
    collector_type: str
    config: dict = {}
    schedule_minutes: int = 0


# ---- checklist / controls ----
@app.post("/api/checklist/import")
async def checklist_import(file: UploadFile = File(...), db: Session = Depends(get_db)):
    try:
        created = import_csv(db, await file.read())
    except ValueError as e:
        raise HTTPException(400, str(e))
    return [{"id": c.id, "code": c.code, "name": c.name,
             "suggested_collector": _keyword_suggest(c)} for c in created]


@app.post("/api/checklist/seed")
def checklist_seed(db: Session = Depends(get_db)):
    """Load the built-in SOC 2 starter checklist (idempotent)."""
    created = seed_controls(db, models.Control)
    return {"created": len(created)}


@app.get("/api/controls")
def list_controls(db: Session = Depends(get_db)):
    out = []
    for c in db.query(models.Control).all():
        out.append({"id": c.id, "framework": c.framework, "code": c.code, "name": c.name,
                    "description": c.description, "suggested_collector": _keyword_suggest(c),
                    "bindings": [{"id": b.id, "collector_type": b.collector_type,
                                  "schedule_minutes": b.schedule_minutes} for b in c.bindings]})
    return out


@app.get("/api/collectors")
def list_collectors():
    return list(REGISTRY)


@app.post("/api/controls/{control_id}/draft-config")
def draft_config(control_id: int, collector_type: str, db: Session = Depends(get_db)):
    """Config author (AI): draft a collector config for this control."""
    c = db.get(models.Control, control_id)
    if not c:
        raise HTTPException(404, "control not found")
    return {"config": agent.draft_config(c, collector_type)}


@app.post("/api/controls/{control_id}/suggest-collector")
def suggest_collector_ai(control_id: int, db: Session = Depends(get_db)):
    """Mapper (AI): pick the best collector for this control, on demand.
    Kept off the controls list so a page load doesn't fire one LLM call per control."""
    c = db.get(models.Control, control_id)
    if not c:
        raise HTTPException(404, "control not found")
    return {"collector_type": suggest_collector(c)}


# ---- bindings ----
@app.post("/api/bindings")
def create_binding(body: BindingIn, db: Session = Depends(get_db)):
    if not db.get(models.Control, body.control_id):
        raise HTTPException(404, "control not found")
    if body.collector_type not in REGISTRY:
        raise HTTPException(400, f"unknown collector_type (have {list(REGISTRY)})")
    b = models.Binding(**body.model_dump())
    db.add(b)
    db.commit()
    scheduler.reload()
    return {"id": b.id}


@app.post("/api/bindings/{binding_id}/run")
def trigger_run(binding_id: int, db: Session = Depends(get_db)):
    run = run_binding(db, binding_id)
    return {"run_id": run.id, "status": run.status, "message": run.message}


# ---- runs / evidence ----
@app.get("/api/runs")
def list_runs(db: Session = Depends(get_db)):
    out = []
    for r in db.query(models.Run).order_by(models.Run.id.desc()).all():
        out.append({"id": r.id, "binding_id": r.binding_id, "status": r.status,
                    "message": r.message, "started_at": r.started_at.isoformat(),
                    "assessment": r.assessment,
                    "evidence": [{"id": e.id, "filename": e.filename, "sha256": e.sha256}
                                 for e in r.evidence]})
    return out


@app.get("/api/evidence")
def list_evidence(db: Session = Depends(get_db)):
    """Flat evidence library across all runs, newest first."""
    rows = (db.query(models.Evidence, models.Run, models.Control)
            .join(models.Run, models.Evidence.run_id == models.Run.id)
            .join(models.Binding, models.Run.binding_id == models.Binding.id)
            .join(models.Control, models.Binding.control_id == models.Control.id)
            .order_by(models.Evidence.id.desc()).all())
    return [{"id": e.id, "filename": e.filename, "sha256": e.sha256,
             "control_code": c.code, "run_id": r.id,
             "collected_at": e.collected_at.isoformat(),
             "sample": bool((e.meta or {}).get("sample"))} for e, r, c in rows]


@app.get("/api/evidence/{evidence_id}/download")
def download_evidence(evidence_id: int, db: Session = Depends(get_db)):
    e = db.get(models.Evidence, evidence_id)
    if not e:
        raise HTTPException(404, "not found")
    return FileResponse(e.path, filename=e.filename)


@app.get("/api/integrity")
def verify_integrity(db: Session = Depends(get_db)):
    """Re-verify chain of custody: re-read every stored evidence file, recompute its
    SHA-256, compare to the hash recorded at collection. Catches tampering or loss."""
    import hashlib
    items, counts = [], {"ok": 0, "tampered": 0, "missing": 0}
    for e in db.query(models.Evidence).all():
        if not os.path.exists(e.path):
            state = "missing"
        else:
            with open(e.path, "rb") as f:
                state = "ok" if hashlib.sha256(f.read()).hexdigest() == e.sha256 else "tampered"
        counts[state] += 1
        items.append({"id": e.id, "filename": e.filename, "sha256": e.sha256, "state": state})
    return {"counts": counts, "items": items}


@app.get("/api/export")
def export_evidence(since: str = None, db: Session = Depends(get_db)):
    """Download the full audit package: evidence files + manifest (chain of custody).
    Optional ?since=YYYY-MM-DD scopes to an audit period."""
    dt = None
    if since:
        try:
            dt = datetime.fromisoformat(since)
        except ValueError:
            raise HTTPException(400, "since must be ISO date, e.g. 2025-01-01")
    data, filename = build_export(db, since=dt)
    return Response(data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
