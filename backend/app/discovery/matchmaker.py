"""Control -> asset matching. Deterministic and auditable: a control's significant
terms are expanded through a compliance synonym map and matched against an asset's
name/path/text, and the reason *names the signals that hit*. No LLM, no confidence
percentage — an LLM's self-reported confidence is not calibrated and a green "96%"
badge is worse than no badge in an audit tool (DISCOVERY_PLAN.md §6).

`rank()` is the seam where an optional LLM rerank can be added later: it would take the
top deterministic candidates and rewrite only their `reason`, never their score.
"""
import re
import time

MIN_SCORE = 0.2      # below this, the control is reported uncovered rather than mis-matched
POSSIBLE = 0.35      # at/above this a match is worth showing even alongside stronger ones

# Concept buckets. A control "has" a concept when one of its roots appears in the control
# text; the asset "evidences" it when one of its tokens starts with one of the roots
# (roots are deliberate prefixes: "polic" covers policy/policies/policy-making).
_SYNONYMS = {
    "access":       ["access", "iam", "identity", "login", "authentic", "password", "credential", "privilege"],
    "mfa":          ["mfa", "multifactor", "multi factor", "2fa", "two factor", "token"],
    "encryption":   ["encrypt", "sse", "kms", "tls", "cipher", "at rest"],
    "logging":      ["log", "audit", "trail", "monitor", "siem", "alert"],
    "incident":     ["incident", "breach", "remediat", "escalat", "forensic", "response"],
    "vendor":       ["vendor", "third party", "third-party", "subprocessor", "supplier", "supply"],
    "backup":       ["backup", "recover", "restore", "continuity", "disaster", "failover"],
    "training":     ["training", "awareness", "education", "onboarding"],
    "policy":       ["polic", "procedure", "standard", "charter", "guideline", "sop", "baseline"],
    "risk":         ["risk", "assessment", "register", "threat", "mitigation"],
    "change":       ["change", "deploy", "release", "pipeline", "code review", "approval"],
    "vulnerability": ["vulnerab", "scan", "patch", "advisory", "cve", "penetration"],
    "conduct":      ["conduct", "ethic", "behaviour", "behavior", "integrity", "conflict"],
    "privacy":      ["privacy", "gdpr", "data protection", "retention", "consent", "pii"],
    "personnel":    ["personnel", "employee", "staff", "hiring", "background", "termination"],
    "availability": ["availability", "uptime", "sla", "capacity", "resilience", "rto", "rpo"],
    "governance":   ["governance", "oversight", "board", "committee", "responsib", "accountab"],
    "classification": ["classif", "confidential", "sensitive", "label", "handling"],
}

_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "are", "must", "including", "include",
    "such", "all", "any", "its", "has", "have", "from", "into", "their", "other", "per",
    "each", "which", "when", "where", "should", "will", "been", "more", "than", "access",
    "control", "controls", "system", "systems", "organization", "organisations", "only",
    "used", "use", "including", "based", "ensure", "ensures", "made", "allowed", "least",
    # Words that appear in nearly every control description: they match every document
    # equally, so as signals they carry no discrimination — only noise in the reason.
    "evidence", "information", "documented", "documentation", "documents", "document",
    "assets", "asset", "appropriate", "periodically", "annually", "regularly",
}

# Prefix roots are deliberately loose ("polic" -> policy/policies/procedures), which
# means a short root can collide with an unrelated word. "log" is the one that bites:
# it matches "logical", so an access-control document scored as a logging match. These
# tokens are barred from every root. ("login" is NOT barred — the access bucket wants it.)
_NEVER_MATCH = {"logical"}


def _norm(text):
    """Lowercase and flatten separators so 'Third-Party_Policy.md' matches 'third party'."""
    return re.sub(r"[-_/.\\]+", " ", (text or "").lower())


def _tokens(text):
    return re.findall(r"[a-z0-9]+", text)


def _asset_haystack(asset):
    return _norm(" ".join([asset.get("source_name", ""), asset.get("path", ""), asset.get("text", "")]))


def _root_hits(roots, tokens, haystack):
    """A concept is evidenced if a token starts with a root, or a multi-word root
    appears in the flattened haystack."""
    for r in roots:
        if " " in r:
            if r in haystack:
                return True
        elif any(t.startswith(r) for t in tokens if t not in _NEVER_MATCH):
            return True
    return False


def score(control, asset):
    """(score, reason, signals) for one control/asset pair. Deterministic."""
    ctrl_hay = _norm(f"{control.code} {control.name} {control.description}")
    ctrl_tokens = set(_tokens(ctrl_hay))
    asset_hay = _asset_haystack(asset)
    asset_tokens = set(_tokens(asset_hay))

    concepts = [k for k, roots in _SYNONYMS.items()
                if _root_hits(roots, ctrl_tokens, ctrl_hay)]
    concept_hits = [k for k in concepts
                    if _root_hits(_SYNONYMS[k], asset_tokens, asset_hay)]

    covered = {r for k in concepts for r in _SYNONYMS[k]}
    keywords = [t for t in ctrl_tokens
                if len(t) > 3 and t not in _STOPWORDS and not any(t.startswith(r) for r in covered)]
    keyword_hits = [k for k in keywords if any(t.startswith(k) for t in asset_tokens)]

    # Weight concepts over loose words, and don't dilute a control that simply names many
    # concepts: >=3 evidenced concepts is treated as a full match.
    hit = len(concept_hits) + 0.5 * len(keyword_hits)
    value = round(min(1.0, hit / max(len(concepts), 3)), 3)

    matched = concept_hits + keyword_hits
    signals = {
        "matched_terms": matched,
        "surface": asset["surface"],
        "ext": asset.get("ext"),
        "age_days": _age_days(asset),
        "tier": _tier(asset["surface"]),
    }
    reason = ("matched evidence signals: " + ", ".join(matched)) if matched else "no signals matched"
    return value, reason, signals


def _age_days(asset):
    if not asset.get("modified"):
        return None
    return max(0, int((time.time() - asset["modified"]) / 86400))


def _tier(surface):
    """How directly the asset evidences the control. Cloud/code API output returns the
    control's parameters verbatim; a written document asserts them."""
    return "direct" if surface in ("cloud", "code") else "documentary"


def _binding_for(asset):
    """The collector + config that would collect this asset. Catalog descriptors
    (Surface B) arrive pre-wired; a discovered document (Surface A) is paired with
    local_file here. Surface C adds its own case."""
    if asset.get("collector_type"):
        return asset["collector_type"], asset["config"]
    return "local_file", {"path": asset["path"]}


def rank(controls, assets, min_score=MIN_SCORE, top_per_control=5):
    """Ordered candidate dicts (ready to become DiscoveryCandidate rows), best first.
    Ties broken by freshness so a newer document outranks a stale one."""
    out = []
    for control in controls:
        scored = []
        for asset in assets:
            value, reason, signals = score(control, asset)
            if value >= min_score:
                scored.append((value, asset, reason, signals))
        scored.sort(key=lambda row: (-row[0], row[3].get("age_days") or 0))
        # A single-signal match ("AWS IAM account summary" hitting only on "access")
        # is only worth showing when it's the best there is. If anything plausible
        # exists for this control, drop the noise rather than padding the list.
        if any(row[0] >= POSSIBLE for row in scored):
            scored = [row for row in scored if row[0] >= POSSIBLE]
        for value, asset, reason, signals in scored[:top_per_control]:
            collector_type, config = _binding_for(asset)
            out.append({
                "control_id": control.id,
                "surface": asset["surface"],
                "source_name": asset["source_name"],
                "collector_type": collector_type,
                "config": config,
                "score": value,
                "reason": reason,
                "signals": signals,
            })
    return out
