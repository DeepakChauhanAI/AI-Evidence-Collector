"""AI agent roles. All reasoning lives here; the collectors stay deterministic.
Each function degrades safely when the LLM isn't configured so the app never
blocks on it. Built on the shared llm.complete / llm.extract_json helpers.

Roles:
  draft_config    (config author)       control -> collector config JSON
  assess_evidence (validator/summarizer) raw evidence -> does it satisfy the control?
  plan_collection (autonomous planner)   natural-language goal -> collector + config
The mapper role (control -> collector_type) lives in checklist.suggest_collector.
"""
from . import llm

# Shape hints so the planner/author emit configs the real collectors accept.
_COLLECTOR_SHAPES = {
    "http_api": '{"url": "...", "method": "GET", "headers": {}}',
    "document": '{"url": "...", "filename": "optional.pdf"}',
    "screenshot": '{"url": "...", "full_page": true}',
}


def draft_config(control, collector_type):
    """Config author: draft a collector config for a control. Returns a dict, or
    {} if the LLM is off or fails (caller falls back to a template)."""
    if not llm.is_configured():
        return {}
    shape = _COLLECTOR_SHAPES.get(collector_type, "{}")
    try:
        out = llm.complete(
            f"You write a JSON config for the '{collector_type}' evidence collector. "
            f"The config must match this shape: {shape}. Use a realistic placeholder URL for "
            f"the system that would hold this evidence. Reply with ONLY the JSON object.",
            f"Control {control.code} — {control.name}: {control.description}",
            max_tokens=500,
        )
        cfg = llm.extract_json(out)
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        return {}


def assess_evidence(control, evidence_texts):
    """Validator/summarizer: judge whether collected evidence satisfies the control.
    Returns {satisfied: bool, summary, gaps, confidence} or None if LLM off/failed.
    evidence_texts: list of (filename, text) — text may be truncated/binary-noted."""
    if not llm.is_configured():
        return None
    joined = "\n\n".join(f"--- {name} ---\n{text[:4000]}" for name, text in evidence_texts) or "(no readable text)"
    try:
        out = llm.complete(
            "You are a SOC 2 auditor reviewing collected evidence against a control. "
            "Decide if the evidence satisfies the control. Reply with ONLY JSON: "
            '{"satisfied": true|false, "summary": "one-line finding", '
            '"gaps": "what is missing, or empty", "confidence": 0.0-1.0}.',
            f"Control {control.code} — {control.name}: {control.description}\n\nEvidence:\n{joined}",
            max_tokens=400,
        )
        v = llm.extract_json(out)
        if not isinstance(v, dict) or "satisfied" not in v:
            return None
        return {
            "satisfied": bool(v.get("satisfied")),
            "summary": str(v.get("summary", "")).strip(),
            "gaps": str(v.get("gaps", "")).strip(),
            "confidence": max(0.0, min(1.0, float(v.get("confidence", 0.5)))) if _num(v.get("confidence")) else 0.5,
        }
    except Exception:
        return None


def plan_collection(goal, collectors):
    """Autonomous planner: turn a natural-language goal into a concrete
    {collector_type, config}. Raises if LLM off or the plan is unusable — the
    caller surfaces that as a failed run (an auditable record, not a crash)."""
    if not llm.is_configured():
        raise RuntimeError("agent collector needs an LLM (set AI_API_KEY)")
    shapes = "\n".join(f"- {c}: {_COLLECTOR_SHAPES.get(c, '{}')}" for c in collectors)
    out = llm.complete(
        "You plan how to collect audit evidence. Choose one collector and write its config. "
        f"Available collectors and their config shapes:\n{shapes}\n"
        'Reply with ONLY JSON: {"collector_type": "<one>", "config": { ... }}.',
        f"Goal: {goal}",
        max_tokens=500,
    )
    plan = llm.extract_json(out)
    ct = plan.get("collector_type")
    cfg = plan.get("config")
    if ct not in collectors or not isinstance(cfg, dict):
        raise RuntimeError(f"agent produced an unusable plan: {plan}")
    return ct, cfg


def _num(x):
    try:
        float(x)
        return True
    except (TypeError, ValueError):
        return False
