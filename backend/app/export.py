"""Audit export: bundle collected evidence + AI assessments + hashes into one ZIP
the auditor can be handed. Pure stdlib (zipfile), builds in memory. The manifest is
the chain of custody — control, evidence filename, SHA-256, and the AI verdict."""
import io
import json
import os
import zipfile
from datetime import datetime, timezone
from .models import Control


def _latest_run(binding):
    return max(binding.runs, key=lambda r: r.id, default=None)


def build_export(db, since=None):
    """Return (zip_bytes, filename). Optional `since` (datetime) keeps only controls
    whose latest run is on/after that time — scope an export to an audit period. ZIP layout:
      manifest.json              — machine-readable chain of custody
      MANIFEST.txt               — human-readable summary
      evidence/<CODE>/<file>     — the artifacts themselves
    """
    now = datetime.now(timezone.utc)
    manifest = {"generated_at": now.isoformat(), "framework": "SOC2",
                "since": since.isoformat() if since else None, "controls": []}
    lines = [f"SOC 2 Evidence Export — generated {now.strftime('%Y-%m-%d %H:%M UTC')}", "=" * 60, ""]

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for c in db.query(Control).order_by(Control.code).all():
            entry = {"code": c.code, "name": c.name, "status": "no_collector", "evidence": [], "assessment": None}
            # newest run across all this control's bindings
            runs = [_latest_run(b) for b in c.bindings]
            runs = [r for r in runs if r]
            latest = max(runs, key=lambda r: r.id) if runs else None
            if since and latest and latest.started_at < since:
                continue  # evidence predates the requested audit window
            if latest:
                entry["assessment"] = latest.assessment
                if latest.assessment:
                    entry["status"] = "satisfied" if latest.assessment.get("satisfied") else "gap"
                elif latest.status == "success":
                    entry["status"] = "collected"
                else:
                    entry["status"] = "failed"
                for ev in latest.evidence:
                    arc = f"evidence/{c.code}/{ev.filename}"
                    if os.path.exists(ev.path):
                        z.write(ev.path, arc)
                    entry["evidence"].append({"file": arc, "sha256": ev.sha256})

            manifest["controls"].append(entry)
            verdict = ""
            if entry["assessment"]:
                a = entry["assessment"]
                verdict = f" — AI: {'SATISFIED' if a.get('satisfied') else 'GAP'} ({a.get('summary','')})"
            lines.append(f"[{entry['status'].upper():12}] {c.code}  {c.name}{verdict}")
            for e in entry["evidence"]:
                lines.append(f"               {e['file']}  sha256={e['sha256']}")

        summary = _counts(manifest["controls"])
        lines[2:2] = [f"Satisfied: {summary['satisfied']}  Gaps: {summary['gap']}  "
                      f"Collected: {summary['collected']}  Not ready: {summary['not_ready']}  "
                      f"(of {len(manifest['controls'])} controls)", ""]
        manifest["summary"] = summary
        z.writestr("manifest.json", json.dumps(manifest, indent=2))
        z.writestr("MANIFEST.txt", "\n".join(lines) + "\n")

    buf.seek(0)
    return buf.getvalue(), f"soc2-evidence-{now.strftime('%Y%m%d-%H%M')}.zip"


def _counts(controls):
    out = {"satisfied": 0, "gap": 0, "collected": 0, "not_ready": 0}
    for c in controls:
        key = c["status"] if c["status"] in out else "not_ready"
        out[key] += 1
    return out
