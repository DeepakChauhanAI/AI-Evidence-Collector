# Evidence Collection Agent — UI/UX Redesign Design

**Date:** 2026-10-07
**Status:** Approved for planning
**Scope:** Front-end redesign to production grade, plus one small backend endpoint.

## Goal

Take the working prototype (3 flat views: Controls · Activity · Collectors) to a
production-grade product comparable in structure to Drata / Vanta / Secureframe,
while keeping our distinctive editorial identity. Approach **C**: keep the visual
identity (oxblood seal, Space Grotesk, dark instrument sidebar, cool off-white
canvas), adopt the interaction ergonomics the players nailed (soft-shadow cards,
generous whitespace, calm data density, smooth states).

## Non-goals (deliberately out of scope)

- Policies / Personnel modules — different data model (HR, policy docs), scope creep away from the collector engine.
- Router library, chart library, any new runtime dependency.
- Backend model changes. Only one new read endpoint.
- Multi-user auth (tracked separately).

## Navigation & app shell

Dark instrument sidebar stays. Nav items:

- **Dashboard** (new) — landing view
- **Controls** (upgraded — grouped + drill-down)
- **Evidence** (new library)
- **Activity** (function unchanged, visual pass)
- **Sources** (reframed Collectors)

View switching stays a `view` state switch (no router lib — native, sufficient).

**Code structure:** `App.jsx` (~450 lines) is split for maintainability since we
add 2 views and grow 2:

- `src/App.jsx` — shell, nav, shared data fetch (`/controls`, `/runs`, `/collectors`), toast, token gate, view routing only.
- `src/views/` — `Dashboard.jsx`, `Controls.jsx`, `Evidence.jsx`, `Activity.jsx`, `Sources.jsx`.
- `src/components/` — shared: `api.js` (fetch + token helpers), `Donut.jsx`, `StatusChip.jsx`, `ProgressBar.jsx`, `Card.jsx`, `BindModal.jsx`.
- `src/lib/readiness.js` — the derivation helpers (`readiness`, `ageDays`, `ageLabel`, `STALE_DAYS`, status→label maps) extracted so Dashboard and Controls share one source of truth.

## Dashboard (new landing view)

All derived client-side from existing `/controls` + `/runs`. No backend change.

- **Readiness hero:** SVG donut (~15 lines, one `<circle>` + `stroke-dasharray`,
  no chart lib) showing % ready = satisfied ÷ total controls, big number in Space
  Grotesk. Compact legend beside it: satisfied / gaps / stale / collected /
  not-ready — the existing `readiness()` tally promoted to hero.
- **Needs attention:** list of controls that are `gap`, `stale`, or `failed`,
  each a clickable row deep-linking into that control's drill-down. Includes the
  existing "Recollect stale" action.
- **Framework progress:** thin bar per SOC 2 category (CC1…CC9) showing ready
  count per group. Reuses Controls grouping.
- **Recent activity:** last 5 runs, condensed; links to full Activity.

## Controls (upgraded)

- **Grouped by SOC 2 category** (CC1 Control Environment … CC9), derived from the
  `code` prefix client-side. Group header shows ready-count + mini progress bar.
- **Search + status filter:** free-text over code/name/description + filter chips
  (All / Gaps / Stale / Satisfied / Uncovered), reusing readiness status.
- **Row:** keeps status chip + age chip; cleaner density.
- **Drill-down panel:** right slide-over (not a route). Shows description, all
  bindings, full run history (not just latest), latest AI verdict, evidence files
  with freshness + integrity badges, and Map-collector / Run actions. `BindModal`
  becomes an action inside this panel.

## Evidence Library (new)

- **New endpoint:** `GET /api/evidence` — flat list: `{id, filename, sha256,
  control_code, run_id, collected_at, sample}` (sample from `meta.sample`). Small
  addition to `main.py`, mirrors existing serialization patterns.
- **Surface:** searchable table — filename, control, collected date, freshness
  badge (reuse `ageDays`), integrity badge, sample-vs-real tag for AWS, download.
- **Integrity:** table shows state; a "Verify all" button calls `/api/integrity`
  and annotates rows (ok / tampered / missing).
- **Preview:** inline for text/JSON/image via existing download URL; others download.

## Sources (reframed Collectors)

Same `/collectors` data as source tiles: icon per type (AWS, HTTP, Document,
Screenshot, Agent), count of controls fed, one-line "what it pulls." Keeps the
"few collectors, many controls" story. Visual pass, no new data.

## Design system (the C polish layer, global in `index.css`)

- **Keep:** `--seal` oxblood, Space Grotesk / Inter / JetBrains Mono, dark
  sidebar, cool off-white canvas, hairline language.
- **Add ergonomics:** card elevation scale (soft shadows on primary surfaces,
  replacing some flat hairlines), looser padding/whitespace rhythm on a 4px scale,
  unified status-color system across chips/badges/bars, hover/focus/transition
  states on all interactive elements, skeleton loading states, per-view empty
  states, existing toast system retained.
- **Shared components:** Donut, ProgressBar, StatusChip, Card — consistent everywhere.

## Backend footprint (tiny by design)

- One new endpoint: `GET /api/evidence`.
- Everything else is client-side reorganization of existing `/controls`, `/runs`,
  `/collectors`, `/integrity`.
- No model changes, no new dependencies.

## Build sequence (each step ends with a build + quick live check)

1. Split `App.jsx` → shell + `views/` + `components/` + `lib/`. No behavior
   change; verify app works identically before touching visuals.
2. Design-system pass in `index.css` + shared components (Donut, StatusChip,
   ProgressBar, Card).
3. Dashboard view.
4. Controls upgrade (grouping, search/filter, drill-down panel).
5. `GET /api/evidence` + Evidence Library view.
6. Sources reframe.
7. Final polish pass (states, empties, responsive).

## Success criteria

- All existing behavior preserved (seed, import, bind, run, recollect, export,
  integrity) — verified live after the split and at the end.
- `npm run build` clean at every step.
- Backend `python -m app.selfcheck` still passes (only additive endpoint).
- New surfaces (Dashboard, Evidence) render with real seeded data in a live check.
- Visual direction C applied consistently: identity kept, ergonomics added.
