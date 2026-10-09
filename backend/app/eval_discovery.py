"""Measure the deterministic matchmaker against the SOC 2 starter checklist.

    python -m app.eval_discovery            # write the review sheet (CSV)
    python -m app.eval_discovery --score    # read the verdicts, print metrics

The sheet is CSV with one row per suggestion, best-ranked first within each control:
    control_code, control_name, rank, score, tier, collector, source_name, reason, verdict

Fill the `verdict` column by hand: y = this suggestion is right, n = wrong. Then --score.

Why this exists: before paying for an LLM rerank, find out whether the deterministic
matcher is wrong *often enough* to be worth it — and, when it is wrong, whether the right
answer was ranked badly (a rerank fixes that) or missing from the list entirely (a rerank
cannot; that needs better discovery coverage). Those two failure modes look identical in
a precision number and have completely different fixes.

Offline by default: local documents + the Surface B descriptor catalogue. The web surface
is a live crawl, so it is opt-in via DISCOVERY_WEB_URL and excluded from a repeatable run.
"""
import csv
import os
import sys

from .db import Base, engine, SessionLocal
from . import models
from .discovery import catalog, document_scanner, matchmaker
from .soc2_starter import seed_controls

SHEET = os.path.join(os.path.dirname(__file__), "..", "eval_discovery_review.csv")

HEADER = ["control_code", "control_name", "rank", "score", "tier",
          "collector", "source_name", "reason", "verdict"]


def _assets(root):
    docs = document_scanner.discover(root or os.getenv("DISCOVERY_DOCS_DIR", "./compliance_docs"))
    items = docs + catalog.discover()
    web = os.getenv("DISCOVERY_WEB_URL", "").strip()
    if web:
        from .discovery import web_crawler
        items += web_crawler.discover(web)
    return items


def _rows(root=None):
    """One row per suggestion, ranked within each control."""
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        seed_controls(db, models.Control)
        controls = db.query(models.Control).order_by(models.Control.code).all()
        assets = _assets(root)
        rows = []
        for c in controls:
            for rank, cand in enumerate(matchmaker.rank([c], assets), start=1):
                rows.append({
                    "control_code": c.code, "control_name": c.name, "rank": rank,
                    "score": cand["score"], "tier": cand["signals"]["tier"],
                    "collector": cand["collector_type"], "source_name": cand["source_name"],
                    "reason": cand["reason"].replace("matched evidence signals: ", ""),
                    "verdict": "",
                })
        return controls, assets, rows
    finally:
        db.close()


def _existing_verdicts():
    """Labels already applied, keyed by (control_code, source_name).

    Regenerating the sheet after a matcher change must not throw away a labelling pass:
    a pair that still exists keeps its verdict, and only genuinely new rows start blank.
    Ranks and scores are deliberately re-derived — they are the thing being measured.
    """
    if not os.path.exists(SHEET):
        return {}
    with open(SHEET, newline="", encoding="utf-8") as f:
        return {(r["control_code"], r["source_name"]): r["verdict"].strip().lower()
                for r in csv.DictReader(f) if r.get("verdict", "").strip()}


def write_sheet(root=None):
    controls, assets, rows = _rows(root)
    kept = _existing_verdicts()
    carried = 0
    for r in rows:
        v = kept.get((r["control_code"], r["source_name"]), "")
        r["verdict"] = v
        carried += bool(v)
    with open(SHEET, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=HEADER)
        w.writeheader()
        w.writerows(rows)
    print(f"{len(assets)} assets x {len(controls)} controls -> {len(rows)} suggestions")
    print(f"review sheet: {os.path.abspath(SHEET)}")
    if carried:
        print(f"carried over {carried} existing verdict(s); {len(rows) - carried} row(s) need labelling")
    print("then: python -m app.eval_discovery --score")


def score():
    if not os.path.exists(SHEET):
        sys.exit("no review sheet — run without --score first")
    with open(SHEET, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    blank = sum(1 for r in rows if r["verdict"].strip().lower() not in ("y", "n"))
    if blank:
        sys.exit(f"{blank} of {len(rows)} rows still unlabelled — fill the verdict column first")

    # Denominator is every control, not just the ones that got a suggestion. A control
    # with no suggestion at all is the worst outcome, and counting only the sheet's rows
    # would hide it behind a self-congratulatory "17/17 covered".
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        seed_controls(db, models.Control)
        all_codes = [c.code for c in db.query(models.Control).order_by(models.Control.code).all()]
    finally:
        db.close()

    by_control = {}
    for r in rows:
        by_control.setdefault(r["control_code"], []).append(r)
    for rs in by_control.values():
        rs.sort(key=lambda r: int(r["rank"]))

    total = len(all_codes)
    uncovered = [c for c in all_codes if c not in by_control]
    top1_ok = sum(1 for rs in by_control.values() if rs[0]["verdict"].lower() == "y")
    top3_ok = sum(1 for rs in by_control.values()
                  if any(r["verdict"].lower() == "y" for r in rs[:3]))

    # Split the failures by kind — this is the number that decides the LLM question.
    ranking_miss, recall_miss = [], list(uncovered)
    for code, rs in by_control.items():
        if rs[0]["verdict"].lower() == "y":
            continue
        (ranking_miss if any(r["verdict"].lower() == "y" for r in rs) else recall_miss).append(code)

    n = lambda x: f"{x}/{total} ({round(100 * x / total)}%)"
    print(f"\nControls                   : {total}")
    print(f"Got a suggestion at all    : {n(total - len(uncovered))}   (no suggestion: {uncovered})")
    print(f"Top-1 correct              : {n(top1_ok)}")
    print(f"A correct answer in top-3  : {n(top3_ok)}")
    print(f"\nWhere top-1 was wrong ({total - top1_ok} controls):")
    print(f"  ranking miss (right answer IS in the list) : {len(ranking_miss)}  {ranking_miss}")
    print(f"  recall miss  (no correct answer found)     : {len(recall_miss)}  {recall_miss}")

    print(f"\nA rerank can address at most {len(ranking_miss)}/{total} controls "
          f"(it reorders, it does not find).")
    print(f"Recall gaps needing better discovery coverage: {len(recall_miss)}/{total}.")


if __name__ == "__main__":
    score() if "--score" in sys.argv else write_sheet()
