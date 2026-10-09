// Evidence older than this is stale for an audit period. 90d is a common SOC 2
// refresh cadence; tune per engagement.
export const STALE_DAYS = 90;

export function ageDays(iso) {
  return Math.floor((Date.now() - new Date(iso + "Z").getTime()) / 86400000);
}

export function ageLabel(d) {
  if (d <= 0) return "today";
  if (d === 1) return "1d ago";
  return `${d}d ago`;
}

// Latest verdict per control, derived from runs (sorted newest-first by the API).
export function readiness(controls, runs) {
  const map = {};
  for (const c of controls) {
    const ids = new Set(c.bindings.map((b) => b.id));
    if (!ids.size) { map[c.id] = { status: "uncovered" }; continue; }
    const latest = runs.find((r) => ids.has(r.binding_id));
    if (!latest) { map[c.id] = { status: "pending" }; continue; }
    const age = ageDays(latest.started_at);
    const base = latest.assessment
      ? (latest.assessment.satisfied ? "satisfied" : "gap")
      : (latest.status === "success" ? "collected" : "failed");
    // Fresh evidence that satisfied the control goes stale once it ages out.
    const status = (base === "satisfied" || base === "collected") && age > STALE_DAYS ? "stale" : base;
    map[c.id] = { status, a: latest.assessment, age };
  }
  return map;
}

export const STATUS_LABEL = {
  satisfied: "Satisfied", gap: "Gap", collected: "Collected", stale: "Stale",
  pending: "Not run", failed: "Failed", uncovered: "No collector",
};

// How strong a discovery suggestion is — words, not a percentage. The score is a
// deterministic signal count, not a calibrated measurement, and a coloured "96%"
// reads as verified. Shared so the Controls and Discovery views can't drift.
export function matchStrength(score) {
  if (score >= 0.6) return "Strong match";
  if (score >= 0.35) return "Possible match";
  return "Weak match";
}

// SOC 2 category from a control code like "CC6.1" -> "CC6". Non-CC codes group under their prefix.
const CC_NAMES = {
  CC1: "Control Environment", CC2: "Communication & Information", CC3: "Risk Assessment",
  CC4: "Monitoring Activities", CC5: "Control Activities", CC6: "Logical & Physical Access",
  CC7: "System Operations", CC8: "Change Management", CC9: "Risk Mitigation",
  A1: "Availability", C1: "Confidentiality", PI1: "Processing Integrity", P1: "Privacy",
};

export function groupControls(controls) {
  const groups = {};
  for (const c of controls) {
    const key = (c.code.match(/^[A-Za-z]+\d+/) || [c.code])[0];
    (groups[key] = groups[key] || { key, name: CC_NAMES[key] || key, controls: [] }).controls.push(c);
  }
  return Object.values(groups).sort((a, b) => a.key.localeCompare(b.key, undefined, { numeric: true }));
}

// Does a control match the active search text + status filter? Pure so it's testable.
export function matchFilter(control, ready, q, filter) {
  const status = (ready || {}).status;
  if (filter !== "all") {
    if (filter === "gaps" && status !== "gap") return false;
    if (filter === "stale" && status !== "stale") return false;
    if (filter === "satisfied" && !(status === "satisfied" || status === "collected")) return false;
    if (filter === "uncovered" && !(status === "uncovered" || status === "pending" || status === "failed")) return false;
  }
  if (q) {
    const hay = `${control.code} ${control.name} ${control.description || ""}`.toLowerCase();
    if (!hay.includes(q.toLowerCase())) return false;
  }
  return true;
}
