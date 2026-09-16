#!/usr/bin/env python3
"""
ytmon healthcheck. Reports rather than fixes; alerts are fail-soft.

Each check answers a question the ledger alone cannot: is the cron firing, is
it doing work, is any stage silently dead, is the disk about to fill, and is
the NAS growing faster than anyone agreed to.
"""

import importlib.util
import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.quota import pacific_day  # noqa: E402

DB = os.environ.get('YTMON_DB', '/data/ytmon/youtube_monitoring.db')
NAS = '/data/nas_penpen/infosphere/ytmon'
DATA_MOUNT = os.environ.get('YTMON_DATA_MOUNT', '/data')
FREE_GB_FLOOR = 10
NAS_GROWTH_LIMIT = 0.25
STALE_HOURS = 36


def load_notify():
    path = ROOT / 'deploy' / 'notify.py'
    spec = importlib.util.spec_from_file_location('ytmon_notify', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.notify


def checks(con) -> list:
    problems = []

    last = con.execute("""
        SELECT run_id, MAX(finished_at) FROM run_log
         WHERE finished_at IS NOT NULL
    """).fetchone()
    if not last or not last[1]:
        problems.append("No completed run has ever been recorded in run_log.")
        return problems

    run_id, finished = last
    age = datetime.utcnow() - datetime.fromisoformat(finished)
    if age > timedelta(hours=STALE_HOURS):
        problems.append(
            f"Last run finished {age.total_seconds() / 3600:.1f}h ago "
            f"({finished}); the cron may not be firing.")

    stages = {r[0]: (r[1], r[2]) for r in con.execute(
        "SELECT stage, units_spent, items FROM run_log WHERE run_id = ?",
        (run_id,))}
    total_units = sum(u or 0 for u, _ in stages.values())
    if total_units == 0:
        problems.append(f"Last run {run_id} spent 0 units across all stages.")

    discovered = stages.get('discover_uploads', (0, 0))[1] or 0
    comments = stages.get('harvest_comments', (0, 0))[1] or 0
    if discovered > 0 and comments == 0:
        problems.append(
            f"Run {run_id}: discover_uploads found {discovered} new videos but "
            f"harvest_comments recorded 0 comments -- the comment stage may be "
            f"failing silently.")

    # A missing mount must not crash the healthcheck: the other checks still
    # carry information, and a check that dies is indistinguishable from one
    # that passed.
    try:
        free_gb = shutil.disk_usage(DATA_MOUNT).free / 1e9
    except OSError as e:
        problems.append(f"Cannot stat {DATA_MOUNT}: {e}")
    else:
        if free_gb < FREE_GB_FLOOR:
            problems.append(f"Free space on {DATA_MOUNT} is {free_gb:.1f} GB, "
                            f"under the {FREE_GB_FLOOR} GB floor.")

    rows = con.execute("""
        SELECT day, bytes FROM storage_ledger
         WHERE location = 'nas_ytmon' ORDER BY day DESC LIMIT 2
    """).fetchall()
    if len(rows) == 2 and rows[1][1]:
        today_b, prev_b = rows[0][1], rows[1][1]
        growth = (today_b - prev_b) / prev_b
        if growth > NAS_GROWTH_LIMIT:
            problems.append(
                f"NAS usage under ytmon/ grew {growth * 100:.0f}% in a day "
                f"({prev_b / 1e9:.2f} -> {today_b / 1e9:.2f} GB). The NAS is a "
                f"shared resource; check for a runaway backfill.")
    return problems


def main() -> int:
    if not Path(DB).exists():
        print(f"database missing: {DB}", file=sys.stderr)
        return 1
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        problems = checks(con)
    finally:
        con.close()

    if not problems:
        print(f"{datetime.utcnow().isoformat()} healthcheck OK")
        return 0

    body = "\n".join(f"- {p}" for p in problems)
    print(f"{datetime.utcnow().isoformat()} healthcheck FAILED\n{body}",
          file=sys.stderr)
    try:
        notify = load_notify()
        notify(subject=f"[ytmon] healthcheck: {len(problems)} problem(s)",
               body=body, severity="ERROR",
               thread_key=f"ytmon-{pacific_day()}")
    except Exception as e:
        print(f"alerting failed (non-fatal): {e}", file=sys.stderr)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
