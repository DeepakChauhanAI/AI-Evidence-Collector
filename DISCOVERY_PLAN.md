# Multi-Surface Autonomous Evidence Discovery Engine
## Goal, Architecture & Implementation Plan

> **Revision note (v2).** The v1 plan proposed four new backend modules. Reading the
> existing codebase, most of what those modules would do **already exists** (§4). v2 keeps
> the vision and the three-surface architecture, but builds on the collectors and LLM
> seams already in the repo instead of alongside them, promotes candidates into existing
> `Binding` rows instead of inventing a parallel concept, and drops the uncalibrated
> "96% confidence" framing that was the weakest part of v1.

---

## 1. Executive Summary & Vision

The goal of the **Panacea InfoSec AI Evidence Collector** is to eliminate manual effort
throughout the audit lifecycle. Today the system executes scheduled collections, hashes
artifacts (SHA-256), and validates evidence with an LLM auditor — but the *first* step,
**finding which internal resource satisfies each control**, is manual.

This initiative adds a **discovery engine**: it scans the organization's operational
surfaces, locates candidate evidence artifacts, and proposes them against checklist
controls. The auditor confirms; the system then binds and collects exactly as it does
today.

**Scope statement (corrected).** The v1 promise of "zero manual URL entry" was an
overclaim: AWS/GitHub/wiki credentials and a document root must be configured once.
The accurate promise is **"configure each surface once, then enter zero per-control
URLs."** Per-control URL entry is what disappears.

---

## 2. Current Gap vs. Target

```
Current:  Control ──► human finds URL/API, pastes into config ──► run ──► hash ──► validate

Target:   Control ──► engine scans configured surfaces ──► ranked candidates
                       ──► auditor confirms ──► Binding (unchanged run/hash/validate path)
```

Discovery **produces proposed `Binding`s**. It does not change the collection,
hashing, or validation loop — it only fills in the binding config that a human used to
type. This keeps the audited pipeline identical before and after.

---

## 3. Architecture

```
                        ┌──────────── PANACEA DISCOVERY ENGINE ────────────┐
                        │                                                   │
     ┌──────────────────┼───────────────────┬───────────────────────────────┼──────┐
     ▼                  ▼                   ▼                               ▼      │
┌──────────┐   ┌──────────────────┐  ┌──────────────────┐   ┌──────────────────┐  │
│ SURFACE A│   │    SURFACE B     │  │    SURFACE C     │   │   MATCHMAKER     │  │
│ DOCUMENTS│   │ CLOUD & CODE     │  │  WEB & WIKI      │   │ deterministic    │  │
├──────────┤   ├──────────────────┤  ├──────────────────┤   │ term/concept     │  │
│ local    │   │ AWS (service,    │  │ trust center,    │   │ scoring +        │  │
│ folder   │   │  operation)      │  │ sitemap / link   │   │ auditable        │  │
│ + S3*    │   │ catalog +        │  │ filter →         │   │ reason           │  │
│          │   │ existing `aws`   │  │ existing         │   │                  │  │
│          │   │ collector;       │  │ `document` /     │   │                  │  │
│          │   │ `github` coll.   │  │ `screenshot`     │   │                  │  │
└──────────┘   └──────────────────┘  └──────────────────┘   └────────┬─────────┘  │
     │                  │                   │                        │            │
     └──────────────────┴───────────────────┴────────────────────────┘            │
                                        ▼                                          │
                     ┌──────────────────────────────────────┐                     │
                     │  DiscoveryCandidate (staging rows)   │◄────────────────────┘
                     │  control_id, surface, collector_type,│
                     │  config, score, reason, signals,     │
                     │  status: new | bound | dismissed     │
                     └──────────────────┬───────────────────┘
                                        ▼  auditor confirms
                     ┌──────────────────────────────────────┐
                     │  Binding  (existing table, unchanged)│
                     │  → scheduled run → SHA-256 → AI      │
                     │    validator → evidence library      │
                     └──────────────────────────────────────┘
```

\* S3 document scanning is the first post-Phase-1 rung (§8).

---

## 4. What Already Exists — Build On It, Don't Rebuild

v1 proposed new modules for work the repo already does. The corrected plan reuses:

| Capability | Existing code | v2 approach |
| :--- | :--- | :--- |
| AWS config evidence (IAM/KMS/S3/CloudTrail) | `collectors.py` → `aws(config)` — boto3 `{service, operation, params}`, sample fallback without creds | **Reuse.** Surface B discovery emits an `aws` config; no scanner module. |
| Headless web capture | `collectors.py` → `screenshot(config)` (Playwright, lazy import) | **Reuse** for Surface C live dashboards. |
| Fetch a URL policy/report | `collectors.py` → `document()` / `http_api()` | **Reuse** for Surface C links. |
| Control → collector mapping | `checklist.py` → `suggest_collector()` (LLM w/ keyword fallback) | **Extend** — the matchmaker generalizes this same seam. Do not add a third mapper. |
| Control → config drafting | `agent.py` → `draft_config()`; goal → plan → `plan_collection()` | **Reuse** after a candidate is confirmed. |
| Secret handling | `runner.py` → `_resolve_secrets()` expands `"env:VAR"` at run time | **Reuse.** Candidates store `env:VAR` refs, never raw keys. |
| Candidate persistence | — (new) | New `DiscoveryCandidate` table (§6). |

**Net-new backend surface (much smaller than v1):**
- `discovery/document_scanner.py` — local folder scan + optional S3 listing, with
  best-effort text extraction (stdlib for `.docx`, `pypdfium2` for `.pdf`).
- `discovery/matchmaker.py` — deterministic control↔asset scoring.
- `discovery/catalog.py` — Surface B descriptor catalogue.
- `discovery/web_crawler.py` — Surface C sitemap/link crawler.
- `collectors.local_file` / `s3_file` — ~10 and ~25 lines; read a discovered artifact.
- `models.DiscoveryCandidate` — staging rows.
- `eval_discovery.py` — measures the matcher's ranking-vs-recall split (§9).
- Four `/api/discovery/*` endpoints.

---

## 5. The Three Discovery Surfaces

### Surface A — Documents & Knowledge
*Targets: local compliance folder and an S3 bucket (`DISCOVERY_S3_BUCKET`); Drive/SharePoint later.*

- Walk the configured root; index name, path, extension, size, mtime. With a bucket
  configured, list document objects under the prefix too — those bind the `s3_file`
  collector instead of `local_file`, so confirming one fetches the object.
- **Body text extraction** feeds the matcher's `text` signal, so `scan_2024_001.pdf` or
  `Policy_v3_FINAL.docx` still match on what they say:
  - `.md/.txt/.csv` — stdlib.
  - `.docx` — stdlib (`zipfile` + `ElementTree`); it is a ZIP of XML, so **no dependency**.
  - `.pdf` — `pypdfium2` (Apache-2.0, extracted first 25 pages). Optional: absent, parse
    failure, or a scanned page with no text layer all degrade to filename matching.
  - Extraction is best-effort and never fatal. It does not appear to affect the SOC 2
    starter score, whose corpus is `.md` — it exists so **real** corpora (mostly PDF/DOCX
    with `Policy_v3_FINAL`-style names) don't regress to filename-only matching.
- Coverage: `CC6.1 → Access_Control_Policy_2026.pdf`, `CC7.3 → Incident_Response_Plan.pdf`,
  `CC9.1 → Vendor_Risk_Management_SOP.docx`, `CC5.3 → Employee_Code_of_Conduct.pdf`.

### Surface B — Cloud & Code
*Targets: AWS (read-only), GitHub/GitLab orgs.*

- AWS: **no scanner module.** A static catalog of `(service, operation)` descriptors
  (password policy, MFA, S3 encryption, CloudTrail, KMS rotation, GuardDuty) is matched to
  controls; the existing `aws` collector does the pulling.
- GitHub: a `github` collector modeled on `aws` (~30 lines, PAT via `env:GITHUB_TOKEN`) plus
  a descriptor catalog (branch protection, required reviews, workflow scans, secret alerts).
- Coverage: `CC6.1 → aws iam get_account_password_policy`, `CC6.6 → github branch_protection`,
  `CC8.1 → github pull_request_reviews / .github/workflows/ci.yml`, `CC7.2 → aws cloudtrail describe_trails`.

### Surface C — Web, Portal & Wiki
*Targets: public trust center, internal wiki (Confluence/Notion/GitBook), status pages.*

- Given a base URL: fetch `sitemap.xml` (or crawl same-host links, depth-limited), keep URLs
  matching security/compliance paths (`/security`, `/privacy`, `/compliance`, `/soc2`,
  `/policies`, `/subprocessors`, `/sla`).
- Each kept URL becomes a candidate bound to the existing `document` collector; live
  dashboards use `screenshot`.
- Coverage: `CC6.7 → Privacy Notice`, `CC9.2 → Subprocessor registry`, `A1.2 → SLA / status page`.

---

## 6. Matchmaker & Scoring (corrected)

v1 presented LLM self-reported confidence (`0.94`, green "96%") as a measurement. **LLM
self-confidence is not calibrated**, and a green "96% verified" badge is worse than no
badge in a SOC 2 tool — the auditor trusts it and stops looking. v2 changes the model:

**Three-stage pipeline (unchanged shape, different third stage):**

1. **Criteria extraction** — significant terms from `code + name + description`, expanded
   through a small compliance synonym map (access→{iam, mfa, password, credential},
   vendor→{third-party, subprocessor, supplier}, …). Deterministic, free, auditable.
2. **Matching** — score each asset by the *concepts* its name/path satisfies.
3. **Ranking + reason** — emit an ordered list with the **matched signals named** and the
   **surface** it came from. No opaque percentage.

```
score = |concepts_hit| / |concepts_in_control|      # 0.0–1.0, explainable
reason = "matched evidence signals: policy, access, mfa, password"
signals = { matched_terms, surface, ext, age_days }
```

**Presentation tiers** are by *action*, not by trusting a number:

| Tier | Meaning | UI treatment |
| :--- | :--- | :--- |
| **Direct config** | API/descriptor returns the control's parameters verbatim (e.g. password policy JSON) | "Suggested — strong" |
| **Documentary** | A written policy names the topic | "Suggested — review" |
| **Weak** | One generic signal (e.g. a bare "policy" filename hit) | Shown only when nothing stronger exists for that control; otherwise dropped rather than padding the list. Otherwise ranked last, labelled "Weak match" |

- Every label reads **"Suggested"**, never "verified" or a bare percentage.
- `age_days` is surfaced so a 2023 PDF never looks equivalent to a live query.
- **`Auto-Bind` stages, it does not collect.** Confirming creates `Binding` rows; it never
  auto-schedules a run. Collection stays an explicit auditor action.

**LLM rerank** (naming/justification, not scoring) is a documented seam on
`matchmaker.rank()`, applied only to the top-K candidates under a per-scan call budget.
Deferred until the deterministic scorer is measured — v1's unbounded N×M LLM calls
(controls × assets, 60 s each) had no budget and would dominate cost.

---

## 7. API

| Endpoint | Purpose |
| :--- | :--- |
| `GET  /api/discovery/sources` | Configured surfaces + status (path, exists, file count). |
| `POST /api/discovery/scan` | Run a scan across configured surfaces; refresh `new` candidates. |
| `GET  /api/discovery/candidates` | Ranked candidates joined to control code/name. |
| `POST /api/discovery/bind` | Confirm a candidate → create `Binding` (does **not** run it). |

Surfaces are configured by env vars (below), not a settings table:
`DISCOVERY_DOCS_DIR` (default `./compliance_docs`), plus `AWS_*` / `GITHUB_TOKEN` via the
existing `env:VAR` convention when Surfaces B/C land.

---

## 8. Roadmap

| Phase | Scope | Artifacts | Status |
| :--- | :--- | :--- | :--- |
| **1 — Surface A + candidate model** | Local document scan, deterministic matchmaker, `DiscoveryCandidate` staging, `local_file` collector | `discovery/document_scanner.py`, `discovery/matchmaker.py`, `models.py`, `collectors.py` | **done** |
| **2 — API** | The four endpoints above | `main.py` | **done** |
| **3 — Frontend Discovery Center** | Surface status, scan progress, candidate matrix, confirm-to-bind | `frontend/src/views/Discovery.jsx`, sidebar | **done** |
| **4 — Checklist badges** | Suggested-candidate badges in Controls view/sheet | `frontend/src/views/Controls.jsx` | **done** |
| **5 — Surface B** | `github` collector + AWS/GitHub descriptor catalogs | `collectors.py`, `discovery/catalog.py` | **done** |
| **6 — Surface C** | Sitemap/link crawler → `document`/`screenshot` candidates | `discovery/web_crawler.py` | **done** |
| **7 — S3 document discovery** | Bucket listing → `s3_file` collector (binary-safe, unlike the `aws` collector) | `document_scanner.py`, `collectors.py` | **done** |
| **8 — PDF/DOCX body text** | `.docx` via stdlib; `.pdf` via `pypdfium2` | `document_scanner.py` | **done** |
| **9 — Scanned PDFs (vision)** | Render page → vision model, for PDFs with no text layer | `discovery/ocr.py`, `llm.describe_image` | **done** (opt-in) |

**Deliberately out of scope (v1 said otherwise):** auto-scheduling runs on bind;
LLM-generated confidence numbers.

### Phase 9 — vision, and why it is opt-in

Scanned PDFs (signed acknowledgements, photographed policies) have no text layer, so no
parser can read them. They are rendered and read by the vision model instead.

**This is the one place in discovery where document contents leave the machine, so it is
off unless explicitly enabled** (`DISCOVERY_VISION_OCR=true`). Everything else — folder,
S3, the AWS/GitHub catalogues, the web crawl, and text extraction — stays local. Results
are cached under `DISCOVERY_VISION_CACHE` keyed by file hash, so a re-scan does not
re-send pages. It degrades silently: off, unconfigured, unrenderable, or a model error
all fall back to filename matching.

Two probes settled the shape before any of it was written:

- **Gateway vision: PASS.** A synthetic 3-band image (red│green│blue) came back as
  `"red green blue"` *in order* — the gateway forwards `image_url` blocks and
  `deepseek-v4-flash` reads them.
- **Playwright as a renderer: FAIL.** Chromium ships without the PDF viewer plugin —
  direct navigation ends in `Download is starting`, and an `<embed>` renders
  *"Couldn't load plugin."*. The already-installed dependency is **not** a renderer, so
  rendering uses `pypdfium2` (already present for text extraction).

---

## 9. Success Metrics

1. **Zero per-control URL entry** — import a 20-control SOC 2 checklist, get candidate
   suggestions for a majority of controls without typing a URL or API parameter.
2. **Deterministic & auditable** — every candidate records surface, timestamp, matched
   signals, and the asset it came from. No unexplained scores.
3. **No regression to the audit trail** — confirming a candidate produces an ordinary
   `Binding`; the run/hash/validate/export path is byte-for-byte the same as manual entry.

### Measured baseline — SOC 2 starter, 2026-10-08

`python -m app.eval_discovery` writes a review sheet of every suggestion; label the
`verdict` column by hand, then `--score` reports the split. Labels survive regeneration
(keyed by control + asset), so the delta after any matcher change is one command.

| | before catalogue expansion | after |
| :--- | :--- | :--- |
| Controls getting any suggestion | 17/20 (85%) | **18/20 (90%)** |
| Top-1 correct | 12/20 (60%) | **15/20 (75%)** |
| A correct answer in top-3 | 13/20 (65%) | **16/20 (80%)** |
| Ranking misses | 1 | 1 |
| Recall misses | 7 | 4 |

**The decisive finding:** of the 8 controls ranked wrong, only **1** (CC6.3 — "access
reviews" matched a branch-protection rule on the shared word *review*) is a *ranking*
error. The other 7 were *recall* errors — no correct answer was found at all. Adding six
AWS descriptors (CloudWatch alarms, Auto Scaling, Backup vaults, RDS, ELB, Route 53)
closed three of them; the remaining four (board minutes, code-of-conduct acknowledgements,
data-classification policy, training records) are documents no API can evidence.

**Consequence for the LLM rerank:** it would address **1 control in 20**, while the
descriptor additions addressed **3**. The bottleneck at this stage is discovery
*coverage*, not match *judgement* — so the rerank seam stays a seam. Revisit if a
larger corpus shows ranking misses overtaking recall misses.
