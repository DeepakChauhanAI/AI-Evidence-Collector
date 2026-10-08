"""Import a GRC-tool checklist export (CSV) into Controls, and suggest a collector
type per control. The suggestion is a deterministic keyword mapper now; swap in an
LLM mapper later behind the same suggest_collector() signature (the 'hybrid' seam)."""
import csv
import io
from . import llm
from .collectors import REGISTRY
from .models import Control


def import_csv(db, raw_bytes):
    """CSV columns (case-insensitive): code, name, description, framework?.
    Header-driven so most GRC exports map with light renaming."""
    text = raw_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    cols = {c.lower().strip(): c for c in (reader.fieldnames or [])}
    if "code" not in cols or "name" not in cols:
        raise ValueError("CSV must have at least 'code' and 'name' columns")
    created = []
    for row in reader:
        ctrl = Control(
            framework=(row.get(cols.get("framework", ""), "") or "SOC2").strip(),
            code=row[cols["code"]].strip(),
            name=row[cols["name"]].strip(),
            description=(row.get(cols.get("description", ""), "") or "").strip(),
        )
        db.add(ctrl)
        created.append(ctrl)
    db.commit()
    return created


_KEYWORDS = [
    ("document", ["policy", "procedure", "document", "report", "agreement", "plan", "sla"]),
    ("http_api", ["access", "logging", "monitor", "config", "backup", "encryption", "mfa", "user"]),
]


def _keyword_suggest(control):
    hay = f"{control.code} {control.name} {control.description}".lower()
    for collector_type, words in _KEYWORDS:
        if any(w in hay for w in words):
            return collector_type
    return "document"


def suggest_collector(control):
    """Best-guess collector_type for a control. Uses the configured LLM when
    available (AI_API_KEY set), else the deterministic keyword fallback. This is
    the 'hybrid' seam: deterministic collectors do the pulling, the LLM only
    maps control -> collector."""
    if not llm.is_configured():
        return _keyword_suggest(control)
    try:
        options = ", ".join(REGISTRY)
        out = llm.complete(
            f"You map an audit control to the single best evidence collector. "
            f"Available collectors: {options}. Reply with ONLY JSON: {{\"collector\": \"<one>\"}}.",
            f"Control {control.code} - {control.name}: {control.description}",
            max_tokens=50,
        )
        choice = llm.extract_json(out).get("collector")
        return choice if choice in REGISTRY else _keyword_suggest(control)
    except Exception:
        return _keyword_suggest(control)  # LLM optional; never block on it
