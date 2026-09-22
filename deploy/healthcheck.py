#!/usr/bin/env python3
"""
ytmon healthcheck. Reports rather than fixes; alerts are fail-soft.

Each check answers a question the ledger alone cannot: is the cron firing, is
it doing work, is any stage silently dead, is the disk about to fill, and is
the NAS growing faster than anyone agreed to.
"""

import argparse
import importlib.util
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.quota import pacific_day    # noqa: E402
from src.timeutil import utcnow, utcnow_dt  # noqa: E402

DB = os.environ.get('YTMON_DB', '/data/ytmon/youtube_monitoring.db')
NAS = '/data/nas_penpen/infosphere/ytmon'
DATA_MOUNT = os.environ.get('YTMON_DATA_MOUNT', '/data')
FREE_GB_FLOOR = 10
# Growth must be BOTH proportionally large and absolutely large. The ratio
# alone fired every day while the NAS filled from one backup to two (0.16 ->
# 0.36 GB is +121% but only +0.2 GB), which is ramp-up, not a runaway. An
# alert that cries wolf daily is one nobody reads.
NAS_GROWTH_LIMIT = 0.25
NAS_GROWTH_MIN_BYTES = 1_000_000_000
STALE_HOURS = 36
BACKUP_LOG = os.environ.get(
    'YTMON_BACKUP_LOG',
    '/data/home/infosphere/youtube_monitoring/logs/backup.log')
BACKUP_STALE_HOURS = 36


def load_notify():
    path = ROOT / 'deploy' / 'notify.py'
    spec = importlib.util.spec_from_file_location('ytmon_notify', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.notify


def backup_verdict(path: str = None) -> tuple:
    """
    The most recent integrity_check verdict from the backup log.

    Returns (when, result) or (None, reason). Parsing the log rather than
    re-reading the backup file keeps this cheap and, more to the point, checks
    what the backup job actually observed at the time it ran.
    """
    log_path = Path(path or BACKUP_LOG)
    if not log_path.exists():
        return None, 'missing'
    try:
        lines = log_path.read_text(errors='replace').splitlines()
    except OSError as e:
        return None, f'unreadable: {e}'

    for line in reversed(lines):
        match = re.search(
            r'^(\S+)\s+\[backup\]\s+integrity_check:\s*(.+?)\s*$', line)
        if match:
            stamp, result = match.group(1), match.group(2)
            try:
                when = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
                when = when.replace(tzinfo=None)
            except ValueError:
                return None, f'unparseable timestamp: {stamp[:40]}'
            return when, result
    return None, 'no integrity_check line'


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
    age = utcnow_dt() - datetime.fromisoformat(finished)
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

    # A stage that had work queued and spent nothing is the shape of a silent
    # failure: a crash between queueing and calling, a lock collision, an
    # exhausted share. A stage with genuinely nothing due spends 0 legitimately
    # and must not alert, which is why the due count is read rather than
    # assumed.
    for stage, units, note in con.execute("""
            SELECT stage, units_spent, COALESCE(note, '') FROM run_log
             WHERE run_id = ?""", (run_id,)):
        match = re.search(r'due=(\d+)', note)
        if match and int(match.group(1)) > 0 and (units or 0) == 0:
            problems.append(
                f"Run {run_id}: stage {stage} had {match.group(1)} items due "
                f"but spent 0 units -- it may have failed without raising.")

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

    # A backup nobody verified is not a backup. Treated like the NAS mount: a
    # missing log is reported, not fatal, because the rest of the check still
    # carries information.
    when, result = backup_verdict()
    if when is None:
        problems.append(f"No usable backup verdict in {BACKUP_LOG} ({result}).")
    elif result != 'ok':
        problems.append(
            f"Last backup integrity_check returned {result!r} at {when.isoformat()}, "
            f"not 'ok'.")
    else:
        age_h = (utcnow_dt() - when).total_seconds() / 3600
        if age_h > BACKUP_STALE_HOURS:
            problems.append(
                f"Last backup integrity_check is {age_h:.1f}h old "
                f"({when.isoformat()}); the backup job may not be running.")

    rows = con.execute("""
        SELECT day, bytes FROM storage_ledger
         WHERE location = 'nas_ytmon' ORDER BY day DESC LIMIT 2
    """).fetchall()
    if len(rows) == 2 and rows[1][1]:
        today_b, prev_b = rows[0][1], rows[1][1]
        delta = today_b - prev_b
        growth = delta / prev_b
        if growth > NAS_GROWTH_LIMIT and delta > NAS_GROWTH_MIN_BYTES:
            problems.append(
                f"NAS usage under ytmon/ grew {growth * 100:.0f}% "
                f"(+{delta / 1e9:.2f} GB) in a day "
                f"({prev_b / 1e9:.2f} -> {today_b / 1e9:.2f} GB). The NAS is a "
                f"shared resource; check for a runaway backfill.")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description="ytmon healthcheck")
    parser.add_argument('--dry-run', action='store_true',
                        help='Print what would be reported; send no mail.')
    args = parser.parse_args()

    if not Path(DB).exists():
        print(f"database missing: {DB}", file=sys.stderr)
        return 1
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        problems = checks(con)
    finally:
        con.close()

    if not problems:
        print(f"{utcnow()} healthcheck OK")
        return 0

    body = "\n".join(f"- {p}" for p in problems)
    print(f"{utcnow()} healthcheck FAILED\n{body}",
          file=sys.stderr)
    if args.dry_run:
        print("(--dry-run: no mail sent)", file=sys.stderr)
        return 1
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
