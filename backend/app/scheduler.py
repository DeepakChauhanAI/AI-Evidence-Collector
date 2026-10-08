"""APScheduler wiring: one job per binding with schedule_minutes > 0. Reloaded on
startup and whenever bindings change (call reload)."""
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from .db import SessionLocal
from .models import Binding, Run
from .runner import run_binding

scheduler = BackgroundScheduler()


def _job(binding_id):
    db = SessionLocal()
    try:
        run_binding(db, binding_id)
    finally:
        db.close()


def _next_run(db, binding):
    """Preserve cadence across restarts: next fire = last run + interval, not now + interval.
    Without this a long-interval job (e.g. 90 days) resets its clock on every reboot and
    may never fire. Overdue -> fire soon (coalesced to a single catch-up run)."""
    last = (db.query(Run).filter(Run.binding_id == binding.id)
            .order_by(Run.id.desc()).first())
    if not last:
        return None  # never run -> let APScheduler schedule first fire one interval out
    due = last.started_at + timedelta(minutes=binding.schedule_minutes)
    return max(due, datetime.utcnow() + timedelta(seconds=5))


def reload():
    """Rebuild all scheduled jobs from the DB. Idempotent."""
    scheduler.remove_all_jobs()
    db = SessionLocal()
    try:
        for b in db.query(Binding).filter(Binding.schedule_minutes > 0).all():
            kw = {}
            nr = _next_run(db, b)
            if nr:
                kw["next_run_time"] = nr
            scheduler.add_job(_job, "interval", minutes=b.schedule_minutes,
                              args=[b.id], id=f"binding-{b.id}", coalesce=True, **kw)
    finally:
        db.close()


def start():
    if not scheduler.running:
        scheduler.start()
    reload()
