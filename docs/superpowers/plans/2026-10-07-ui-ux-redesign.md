# UI/UX Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Take the working prototype (3 flat views) to a production-grade product — add Dashboard + Evidence Library, upgrade Controls (grouping/search/drill-down), reframe Collectors as Sources, and apply direction C (keep editorial identity, add SaaS ergonomics).

**Architecture:** Split the monolithic `App.jsx` into shell + `views/` + `components/` + `lib/`. All new surfaces derive from existing endpoints client-side; one additive backend endpoint (`GET /api/evidence`). No router lib (view-state switch), no chart lib (SVG donut).

**Tech Stack:** Vite + React 18 (single-switch routing), plain CSS design system in `index.css`, FastAPI backend (one new read endpoint).

**Verification convention (this repo has no test runner):** every task ends with `npm run build` (must be clean) and, for non-trivial pure logic, a `node -e` assert check. Backend changes end with `python -m app.selfcheck`. Live checks start servers by absolute path, kill by PID/port ONLY (never broad taskkill).

---

## File Structure (target)

```
frontend/src/
  App.jsx                 # shell: sidebar nav, shared fetch, token gate, view routing, toast
  main.jsx                # unchanged
  index.css               # design system (evolved)
  lib/
    api.js                # fetch wrapper + token + downloadUrl + exportUrl
    readiness.js          # readiness(), ageDays(), ageLabel(), STALE_DAYS, STATUS_LABEL, groupControls()
  components/
    Donut.jsx             # SVG readiness donut
    ProgressBar.jsx       # thin category/progress bar
    StatusChip.jsx        # status + age chips
    Card.jsx              # elevated surface wrapper
    BindModal.jsx         # existing modal, extracted
  views/
    Dashboard.jsx         # new landing view
    Controls.jsx          # upgraded: grouping, search/filter, drill-down slide-over
    Evidence.jsx          # new library
    Activity.jsx          # extracted, visual pass
    Sources.jsx           # reframed collectors
backend/app/
  main.py                 # + GET /api/evidence
```

---

## Task 1: Extract shared lib + components with NO behavior change

**Files:**
- Create: `frontend/src/lib/api.js`, `frontend/src/lib/readiness.js`
- Create: `frontend/src/components/BindModal.jsx`, `Donut.jsx`, `ProgressBar.jsx`, `StatusChip.jsx`, `Card.jsx`
- Create: `frontend/src/views/Controls.jsx`, `Activity.jsx`, `Sources.jsx`
- Modify: `frontend/src/App.jsx` (import from the new modules; shell + routing only)

This is a pure refactor. The app must look and behave identically after it. Do it before any visual work.

- [ ] **Step 1: Create `lib/api.js`** — move the fetch helpers verbatim from `App.jsx`.

```js
const getToken = () => localStorage.getItem("api_token") || "";

export async function api(path, opts = {}) {
  const res = await fetch("/api" + path, {
    ...opts,
    headers: {
      ...(opts.headers || {}),
      ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}),
    },
  });
  if (res.status === 401) { localStorage.removeItem("api_token"); throw new Error("unauthorized"); }
  return res.json();
}

export const downloadUrl = (id) =>
  `/api/evidence/${id}/download${getToken() ? `?token=${encodeURIComponent(getToken())}` : ""}`;

export const exportUrl = (since) =>
  `/api/export?${since ? `since=${since}&` : ""}${getToken() ? `token=${encodeURIComponent(getToken())}` : ""}`;

export { getToken };
```

- [ ] **Step 2: Create `lib/readiness.js`** — move `STALE_DAYS`, `ageDays`, `ageLabel`, `readiness`, `STATUS_LABEL` verbatim from `App.jsx`, add `groupControls` (new, used by Controls + Dashboard).

```js
export const STALE_DAYS = 90;
export function ageDays(iso) { return Math.floor((Date.now() - new Date(iso + "Z").getTime()) / 86400000); }
export function ageLabel(d) { if (d <= 0) return "today"; if (d === 1) return "1d ago"; return `${d}d ago`; }

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
    const status = (base === "satisfied" || base === "collected") && age > STALE_DAYS ? "stale" : base;
    map[c.id] = { status, a: latest.assessment, age };
  }
  return map;
}

export const STATUS_LABEL = {
  satisfied: "Satisfied", gap: "Gap", collected: "Collected", stale: "Stale",
  pending: "Not run", failed: "Failed", uncovered: "No collector",
};

// SOC 2 category from a control code like "CC6.1" -> "CC6". Non-CC codes group under their prefix.
const CC_NAMES = {
  CC1: "Control Environment", CC2: "Communication & Information", CC3: "Risk Assessment",
  CC4: "Monitoring Activities", CC5: "Control Activities", CC6: "Logical & Physical Access",
  CC7: "System Operations", CC8: "Change Management", CC9: "Risk Mitigation",
};
export function groupControls(controls) {
  const groups = {};
  for (const c of controls) {
    const key = (c.code.match(/^[A-Za-z]+\d+/) || [c.code])[0];
    (groups[key] = groups[key] || { key, name: CC_NAMES[key] || key, controls: [] }).controls.push(c);
  }
  return Object.values(groups).sort((a, b) => a.key.localeCompare(b.key, undefined, { numeric: true }));
}
```

- [ ] **Step 3: Verify `groupControls` logic with a node check.**

Run:
```bash
cd "D:/Project Files/Evidence-Collection-Agent/frontend" && node --input-type=module -e '
import { groupControls } from "./src/lib/readiness.js";
const g = groupControls([{code:"CC6.1",bindings:[]},{code:"CC6.2",bindings:[]},{code:"CC1.4",bindings:[]}]);
console.assert(g.length===2, "two groups");
console.assert(g[0].key==="CC1" && g[1].key==="CC6", "sorted numeric: "+g.map(x=>x.key));
console.assert(g[1].controls.length===2, "CC6 has 2");
console.assert(g[1].name==="Logical & Physical Access", "named");
console.log("OK groupControls");
'
```
Expected: `OK groupControls`

- [ ] **Step 4: Create `components/BindModal.jsx`** — move the entire `BindModal` function from `App.jsx` verbatim; add `import { api } from "../lib/api.js";` and the `CONFIG_TEMPLATES` const (move it too). Export default.

- [ ] **Step 5: Create `components/StatusChip.jsx`** — small presentational component for the status + age chips currently inline in Controls.

```js
import { STATUS_LABEL, ageLabel } from "../lib/readiness.js";
export default function StatusChip({ status, age }) {
  return (
    <>
      <span className={`chip-status ${status}`}>{STATUS_LABEL[status]}</span>
      {age != null && status !== "pending" && <span className="chip-age">{ageLabel(age)}</span>}
    </>
  );
}
```

- [ ] **Step 6: Create `components/Donut.jsx`, `ProgressBar.jsx`, `Card.jsx`** (used from Task 2 on; create now so imports resolve).

```js
// Donut.jsx — pct 0..100
export default function Donut({ pct, label, sub }) {
  const r = 52, c = 2 * Math.PI * r, off = c * (1 - pct / 100);
  return (
    <div className="donut">
      <svg viewBox="0 0 120 120" width="120" height="120">
        <circle cx="60" cy="60" r={r} className="donut-track" />
        <circle cx="60" cy="60" r={r} className="donut-val"
                strokeDasharray={c} strokeDashoffset={off} transform="rotate(-90 60 60)" />
        <text x="60" y="58" className="donut-pct">{pct}%</text>
        <text x="60" y="76" className="donut-cap">{label}</text>
      </svg>
      {sub && <div className="donut-sub">{sub}</div>}
    </div>
  );
}
```

```js
// ProgressBar.jsx
export default function ProgressBar({ value, total }) {
  const pct = total ? Math.round((value / total) * 100) : 0;
  return <div className="pbar"><span style={{ width: pct + "%" }} /></div>;
}
```

```js
// Card.jsx
export default function Card({ title, action, children, className = "" }) {
  return (
    <section className={`card ${className}`}>
      {(title || action) && <header className="card-head"><h3>{title}</h3>{action}</header>}
      <div className="card-body">{children}</div>
    </section>
  );
}
```

- [ ] **Step 7: Create `views/Activity.jsx`** — move the `priorHashes` function and `Activity` component verbatim from `App.jsx`; add `import { downloadUrl } from "../lib/api.js";`. Export default `Activity`.

- [ ] **Step 8: Create `views/Sources.jsx`** — move the `Fleet` function verbatim from `App.jsx`, rename the default export to `Sources` (keep internals). Export default.

- [ ] **Step 9: Create `views/Controls.jsx`** — move the current `Controls` component verbatim from `App.jsx`; import `StatusChip` and use it in place of the inline chip spans; add `import { STALE_DAYS } from "../lib/readiness.js";`. Export default. (Upgrades happen in Task 4 — this step is move-only.)

- [ ] **Step 10: Rewrite `App.jsx`** to import everything and keep only shell + routing + shared fetch + token gate + toast + the `run`/`runStale`/`seed`/`importCsv`/`verifyIntegrity` handlers + readiness/tally computation. Remove the now-moved code. Nav + views labels stay exactly as today (Controls/Activity/Collectors) for this task — renaming/new nav is Task 3.

- [ ] **Step 11: Build and verify no behavior change.**

Run:
```bash
cd "D:/Project Files/Evidence-Collection-Agent/frontend" && npm run build 2>&1 | tail -3
```
Expected: `✓ built in ...` with no errors.

- [ ] **Step 12: Live check — app behaves identically.**

Start backend (background, by absolute path), load the built frontend via a static serve or `npm run dev`, confirm Controls/Activity/Collectors render, seed works, a run works. Then stop backend by PID/port only.

```bash
cd "D:/Project Files/Evidence-Collection-Agent/backend" && DATABASE_URL=sqlite:///./verify.db EVIDENCE_DIR=./verify_store python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --env-file .env
# (background) then:
curl -s -m8 http://127.0.0.1:8000/api/controls -o /dev/null -w "%{http_code}\n"   # 200
# kill: PID=$(netstat -ano | grep ':8000' | grep LISTENING | awk '{print $NF}' | head -1); powershell -Command "Stop-Process -Id $PID -Force"
# rm -f verify.db; rm -rf verify_store
```
Expected: `200`; UI identical to before.

---

## Task 2: Design-system pass in `index.css`

**Files:**
- Modify: `frontend/src/index.css`

Add the ergonomics layer (direction C) without discarding tokens. Additive CSS for the new components + evolved surfaces.

- [ ] **Step 1: Add elevation + spacing tokens** under `:root` (append, don't remove existing):

```css
  --shadow-sm: 0 1px 2px rgba(16,18,22,.04), 0 1px 3px rgba(16,18,22,.06);
  --shadow-md: 0 2px 6px rgba(16,18,22,.06), 0 6px 16px rgba(16,18,22,.08);
  --r-card: 14px;
```

- [ ] **Step 2: Add Card styles.**

```css
.card { background: var(--panel); border: 1px solid var(--line); border-radius: var(--r-card); box-shadow: var(--shadow-sm); }
.card-head { display: flex; align-items: center; justify-content: space-between; padding: 16px 20px; border-bottom: 1px solid var(--line); }
.card-head h3 { font-family: "Space Grotesk"; font-size: 15px; font-weight: 600; margin: 0; letter-spacing: -.01em; }
.card-body { padding: 18px 20px; }
```

- [ ] **Step 3: Add Donut styles.**

```css
.donut { display: inline-flex; flex-direction: column; align-items: center; }
.donut-track { fill: none; stroke: var(--line); stroke-width: 10; }
.donut-val { fill: none; stroke: var(--seal); stroke-width: 10; stroke-linecap: round; transition: stroke-dashoffset .6s ease; }
.donut-pct { text-anchor: middle; font-family: "Space Grotesk"; font-weight: 600; font-size: 22px; fill: var(--text); }
.donut-cap { text-anchor: middle; font-size: 9px; fill: var(--muted); text-transform: uppercase; letter-spacing: .08em; }
.donut-sub { margin-top: 8px; font-size: 12px; color: var(--muted); }
```

- [ ] **Step 4: Add ProgressBar + dashboard grid + search/filter + slide-over + evidence table styles.** (Full CSS block — see Appendix A; paste verbatim.)

- [ ] **Step 5: Build.**

Run: `cd "D:/Project Files/Evidence-Collection-Agent/frontend" && npm run build 2>&1 | tail -3`
Expected: clean build.

---

## Task 3: New navigation + routing in `App.jsx`

**Files:**
- Modify: `frontend/src/App.jsx`

- [ ] **Step 1: Replace nav** — 5 items: `dashboard`, `controls`, `evidence`, `activity`, `sources`. Default `view = "dashboard"`. Labels: Dashboard / Controls / Evidence / Activity / Sources. Counts: controls.length, runs.length, evidence count (controls-derived until Task 5 — use `—` placeholder), collectors.length. Keep the dark sidebar markup.

```jsx
const NAV = [
  ["dashboard", "Dashboard"], ["controls", "Controls"], ["evidence", "Evidence"],
  ["activity", "Activity"], ["sources", "Sources"],
];
```

- [ ] **Step 2: Add view routing** — render `<Dashboard>` / `<Controls>` / `<Evidence>` / `<Activity>` / `<Sources>` by `view`. Pass shared props (controls, runs, ready, collectors, handlers, setView, onBind). Dashboard/Evidence imported in Tasks 4/5 — create empty stub files now returning `<div className="empty"><h3>Coming up</h3></div>` so imports resolve.

- [ ] **Step 3: Build.**
Run: `npm run build 2>&1 | tail -3` — expected clean.

---

## Task 4: Dashboard view + Controls upgrade

**Files:**
- Create/replace: `frontend/src/views/Dashboard.jsx`
- Modify: `frontend/src/views/Controls.jsx`

- [ ] **Step 1: Write `Dashboard.jsx`** — readiness hero (Donut, pct = round(satisfied/total*100)), legend from tally, "Needs attention" list (controls where status in gap/stale/failed; row onClick → `setView("controls")` + select), framework progress (groupControls + ProgressBar per group counting ready), recent activity (runs.slice(0,5), condensed). Props: `{ controls, runs, ready, tally, onRecollect, staleIds, setView, onSelect }`.

```jsx
import Card from "../components/Card.jsx";
import Donut from "../components/Donut.jsx";
import ProgressBar from "../components/ProgressBar.jsx";
import { groupControls } from "../lib/readiness.js";

export default function Dashboard({ controls, runs, ready, tally, onRecollect, staleIds, onSelect }) {
  const total = controls.length || 1;
  const pct = Math.round((tally.satisfied / total) * 100);
  const attention = controls.filter((c) => ["gap", "stale", "failed"].includes((ready[c.id] || {}).status));
  const groups = groupControls(controls);
  return (
    <div className="dash">
      <Card className="dash-hero" title="Audit readiness"
            action={staleIds.length ? <button className="btn sm" onClick={() => onRecollect(staleIds)}>Recollect stale ({staleIds.length})</button> : null}>
        <div className="dash-hero-row">
          <Donut pct={pct} label="ready" />
          <div className="legend">
            <span className="rb satisfied"><b>{tally.satisfied}</b> satisfied</span>
            <span className="rb gap"><b>{tally.gap}</b> gaps</span>
            <span className="rb stale"><b>{tally.stale}</b> stale</span>
            <span className="rb collected"><b>{tally.collected}</b> collected</span>
            <span className="rb uncovered"><b>{tally.uncovered + tally.pending + tally.failed}</b> not ready</span>
          </div>
        </div>
      </Card>
      <Card title={`Needs attention (${attention.length})`}>
        {attention.length ? attention.map((c) => (
          <button className="attn-row" key={c.id} onClick={() => onSelect(c)}>
            <span className="code">{c.code}</span><span className="attn-name">{c.name}</span>
            <span className={`chip-status ${ready[c.id].status}`}>{ready[c.id].status}</span>
          </button>
        )) : <p className="muted">Nothing needs attention. Every covered control is satisfied and fresh.</p>}
      </Card>
      <Card title="Framework coverage">
        {groups.map((g) => {
          const rdy = g.controls.filter((c) => ["satisfied", "collected"].includes((ready[c.id] || {}).status)).length;
          return <div className="cov-row" key={g.key}><span className="cov-name">{g.key} · {g.name}</span>
            <ProgressBar value={rdy} total={g.controls.length} /><span className="cov-n">{rdy}/{g.controls.length}</span></div>;
        })}
      </Card>
    </div>
  );
}
```

- [ ] **Step 2: Wire Dashboard props in `App.jsx`** — pass `tally`, `onRecollect={runStale}`, `staleIds`, `onSelect` (sets a `selected` control state + `view="controls"`).

- [ ] **Step 3: Upgrade `Controls.jsx`** — add search box + filter chips (All/Gaps/Stale/Satisfied/Uncovered), group rows via `groupControls` with a group header (name + ProgressBar), and a right slide-over drill-down panel showing description, bindings, run history (filter runs by this control's binding ids), latest assessment, evidence with freshness/integrity badges, and Map/Run actions. Accept `selected` + `onSelect` props so Dashboard can open a control.

- [ ] **Step 4: Verify filter logic with a node check** (pure function `matchFilter(control, ready, q, filter)` extracted into `readiness.js`).

```bash
cd "D:/Project Files/Evidence-Collection-Agent/frontend" && node --input-type=module -e '
import { matchFilter } from "./src/lib/readiness.js";
const c={code:"CC6.1",name:"Logical Access",description:"mfa",bindings:[]};
console.assert(matchFilter(c,{status:"gap"},"","gaps")===true,"gap passes gaps");
console.assert(matchFilter(c,{status:"gap"},"","satisfied")===false,"gap fails satisfied");
console.assert(matchFilter(c,{status:"gap"},"mfa","all")===true,"text match");
console.assert(matchFilter(c,{status:"gap"},"xyz","all")===false,"text miss");
console.log("OK matchFilter");'
```
Expected: `OK matchFilter`

- [ ] **Step 5: Build + live check** — seed, confirm Dashboard donut + groups render, open a control drill-down, run a collector. Stop backend by PID/port.

---

## Task 5: `GET /api/evidence` + Evidence Library view

**Files:**
- Modify: `backend/app/main.py`
- Create/replace: `frontend/src/views/Evidence.jsx`

- [ ] **Step 1: Add the endpoint** to `main.py` (after `list_runs`):

```python
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
```

- [ ] **Step 2: Verify endpoint** — run selfcheck (ensures imports/app still load) then live check.

```bash
cd "D:/Project Files/Evidence-Collection-Agent/backend" && python -m app.selfcheck 2>&1 | tail -1
```
Expected: the `OK: ...` line.

Live: start backend, seed, bind aws, run, then:
```bash
curl -s -m8 http://127.0.0.1:8000/api/evidence | python -c "import sys,json;d=json.load(sys.stdin);print(len(d),'rows',d[0] if d else '')"
```
Expected: ≥1 row with `control_code`, `collected_at`, `sample`.

- [ ] **Step 3: Write `Evidence.jsx`** — fetch `/api/evidence` on mount, searchable table (filename / control / collected date / freshness badge via `ageDays` / sample tag / integrity state / download via `downloadUrl`). "Verify all" button calls `/api/integrity`, maps `items` by id, annotates rows ok/tampered/missing.

- [ ] **Step 4: Wire evidence count** into the App nav (fetch count or use evidence length once loaded).

- [ ] **Step 5: Build + live check** — Evidence view lists seeded run artifacts; Verify all shows "intact". Stop backend by PID/port, clean verify DB + store.

---

## Task 6: Sources reframe + final polish

**Files:**
- Modify: `frontend/src/views/Sources.jsx`, `frontend/src/index.css`

- [ ] **Step 1: Reframe Sources** — source tiles with an inline SVG/emoji icon per type (aws/http_api/document/screenshot/agent), controls-fed count, one-line blurb (reuse existing `blurb` map + add `aws` and `agent`). Keep the "few collectors, many controls" lead paragraph.

- [ ] **Step 2: Polish pass** — per-view empty states, hover/focus transitions on buttons/rows/tiles, skeleton (simple pulsing block) while `controls`/`runs` first load, responsive check at 820px. All CSS additive.

- [ ] **Step 3: Build.**
Run: `npm run build 2>&1 | tail -3` — expected clean.

- [ ] **Step 4: Full live verification** — start both servers, walk all 5 views with seeded + a live AWS run: Dashboard donut/attention/coverage, Controls grouping/search/filter/drill-down, Evidence library + verify-all, Activity diff chips, Sources tiles. Confirm export + recollect still work. Stop servers by PID/port, clean verify DB + store.

---

## Appendix A — CSS block for Task 2 Step 4

```css
/* dashboard */
.dash { display: grid; gap: 16px; }
.dash-hero-row { display: flex; gap: 28px; align-items: center; }
.legend { display: flex; flex-direction: column; gap: 6px; }
.attn-row { display: flex; align-items: center; gap: 12px; width: 100%; text-align: left; background: none; border: 0; border-bottom: 1px solid var(--line); padding: 10px 2px; }
.attn-row:last-child { border-bottom: 0; }
.attn-row:hover { background: var(--paper); }
.attn-name { flex: 1; font-size: 14px; }
.cov-row { display: grid; grid-template-columns: 1fr 160px 44px; gap: 12px; align-items: center; padding: 7px 0; font-size: 13px; }
.cov-n { font-family: "JetBrains Mono"; font-size: 12px; color: var(--muted); text-align: right; }
.pbar { height: 7px; background: var(--paper); border: 1px solid var(--line); border-radius: 4px; overflow: hidden; }
.pbar span { display: block; height: 100%; background: var(--seal); }
.muted { color: var(--muted); font-size: 13.5px; }
/* controls toolbar */
.ctrl-toolbar { display: flex; gap: 10px; margin-bottom: 16px; flex-wrap: wrap; }
.ctrl-toolbar input { flex: 1; min-width: 200px; border: 1px solid var(--line-2); border-radius: 8px; padding: 9px 12px; font: inherit; font-size: 13.5px; }
.fchip { border: 1px solid var(--line-2); background: var(--panel); border-radius: 999px; padding: 6px 13px; font-size: 12.5px; }
.fchip.on { background: var(--ink); color: #fff; border-color: var(--ink); }
.grp-head { display: flex; align-items: center; gap: 14px; margin: 22px 0 8px; }
.grp-head h4 { font-family: "Space Grotesk"; font-size: 13px; margin: 0; letter-spacing: -.01em; }
.grp-head .pbar { width: 140px; }
/* slide-over */
.sheet-scrim { position: fixed; inset: 0; background: rgba(16,18,22,.4); z-index: 40; }
.sheet { position: fixed; top: 0; right: 0; height: 100vh; width: 540px; max-width: 94vw; background: var(--panel); box-shadow: -16px 0 48px rgba(0,0,0,.2); z-index: 41; overflow-y: auto; animation: slidein .2s ease; }
@keyframes slidein { from { transform: translateX(24px); opacity: .6; } }
.sheet-head { padding: 22px 24px; border-bottom: 1px solid var(--line); }
.sheet-body { padding: 20px 24px; display: flex; flex-direction: column; gap: 18px; }
/* evidence table */
.etable { width: 100%; border-collapse: collapse; font-size: 13.5px; }
.etable th { text-align: left; font-size: 11px; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); padding: 8px 10px; border-bottom: 1px solid var(--line); }
.etable td { padding: 10px; border-bottom: 1px solid var(--line); }
.etable tr:hover td { background: var(--paper); }
.tag { font-size: 10.5px; font-weight: 600; padding: 2px 7px; border-radius: 999px; text-transform: uppercase; letter-spacing: .04em; }
.tag.sample { color: var(--warn); background: var(--warn-soft); }
.tag.real { color: var(--ok); background: var(--ok-soft); }
.tag.ok { color: var(--ok); background: var(--ok-soft); }
.tag.tampered, .tag.missing { color: var(--err); background: var(--err-soft); }
/* source tiles */
.src-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px,1fr)); gap: 14px; }
.src-tile { display: flex; gap: 14px; align-items: flex-start; }
.src-ico { width: 40px; height: 40px; border-radius: 10px; background: var(--seal-soft); color: var(--seal); display: grid; place-items: center; font-family: "JetBrains Mono"; font-weight: 700; font-size: 13px; flex-shrink: 0; }
/* skeleton */
.skel { background: linear-gradient(90deg, var(--line) 25%, var(--paper) 50%, var(--line) 75%); background-size: 200% 100%; animation: shimmer 1.3s infinite; border-radius: 8px; height: 60px; }
@keyframes shimmer { to { background-position: -200% 0; } }
```

---

## Self-Review

**Spec coverage:** shell split → T1; design system → T2; nav → T3; Dashboard → T4; Controls upgrade → T4; `/api/evidence` + Evidence Library → T5; Sources reframe → T6; polish → T6. All spec sections mapped.

**Placeholder scan:** T3 uses an evidence-count `—` placeholder in nav until T5 wires the real count — intentional and resolved in T5 Step 4. Stub Dashboard/Evidence files in T3 Step 2 are replaced in T4/T5. No unresolved placeholders.

**Type consistency:** `readiness()` returns `{status, a, age}`; `tally` keys match `STATUS_LABEL`; `groupControls` → `{key,name,controls}` used identically in Dashboard + Controls; `matchFilter(control, ready, q, filter)` signature consistent T4 Step 3/4; `downloadUrl`/`exportUrl`/`api` imported from `lib/api.js` everywhere.
