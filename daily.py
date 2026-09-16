#!/usr/bin/env python3
"""
Daily monitoring run.

    python daily.py run [--stages ...] [--budget N] [--config ...]
    python daily.py status [--config ...]

`run` emits one JSON line per run on stdout (the report dict), intended for
logs/run.jsonl. `status` prints today's quota spend per endpoint, channels by
tier and status, and the age of the last completed run.

Not to be confused with monitor_collection.py, which is the terminal progress
viewer for collect.py backfills.
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

from src import daily as stages                       # noqa: E402
from src.database import Database, ReplicaRefused     # noqa: E402
from src.lock import advisory_lock, LockUnavailable   # noqa: E402
from src.timeutil import utcnow_dt                    # noqa: E402
from src.quota import (                               # noqa: E402
    QuotaGovernor, pacific_day, DAILY_FORBIDDEN_ENDPOINTS,
)
from src.youtube_client import YouTubeAPIClient       # noqa: E402

DEFAULT_CONFIG = 'config/config_daily.yaml'

logger = logging.getLogger('daily')


def load_config(path: str) -> dict:
    with open(path) as f:
        cfg = yaml.safe_load(f)

    # The key comes from the environment, never from the config file: the
    # config is committed, the key is not.
    key = os.environ.get('YOUTUBE_API_KEY') or (cfg.get('api') or {}).get('youtube_api_key')
    if not key:
        raise SystemExit(
            "No API key. Set YOUTUBE_API_KEY in the environment "
            "(deploy/run_daily.sh sources .env)."
        )
    cfg.setdefault('api', {})['youtube_api_key'] = key
    return cfg


def setup_logging(cfg: dict) -> None:
    log_path = cfg.get('logging', {}).get('file', 'logs/pipeline.log')
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)

    # Under cron, run_daily.sh redirects stderr into this same file, so adding
    # a StreamHandler as well wrote every line twice. Attach it only when
    # stderr is a terminal -- interactively it is the useful half, and under
    # cron stderr still carries anything Python itself did not log, such as an
    # uncaught traceback.
    handlers = [logging.FileHandler(log_path)]
    try:
        if sys.stderr.isatty():
            handlers.append(logging.StreamHandler(sys.stderr))
    except (AttributeError, ValueError):
        pass

    logging.basicConfig(
        level=getattr(logging, cfg.get('logging', {}).get('level', 'INFO')),
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        handlers=handlers,
    )


def open_db(cfg: dict, allow_replica: bool = False) -> Database:
    return Database(db_path=cfg['database']['sqlite_path'],
                    allow_replica=allow_replica)


def cmd_run(args) -> int:
    cfg = load_config(args.config)
    setup_logging(cfg)

    budget = args.budget if args.budget is not None else cfg['quota']['daily_budget']
    if args.max_tier is not None:
        cfg.setdefault('limits', {})['max_tier'] = args.max_tier
    lock_path = cfg.get('lock', {}).get('path', 'data/.ytmon.lock')

    try:
        # Non-blocking: a run that collides with a backfill exits rather than
        # queueing behind it for hours. The cron healthcheck reports it.
        with advisory_lock(lock_path, blocking=False):
            db = open_db(cfg, allow_replica=args.i_know_this_is_a_replica)
            governor = QuotaGovernor(db.conn, budget,
                                     forbidden_endpoints=DAILY_FORBIDDEN_ENDPOINTS)
            client = YouTubeAPIClient(
                api_key=cfg['api']['youtube_api_key'],
                max_retries=cfg.get('api', {}).get('max_retries', 3),
                retry_delay=cfg.get('api', {}).get('retry_delay', 2),
                governor=governor,
                allow_search=False,   # daily path never pays 100 units
            )

            report = stages.run(db.conn, client, cfg, stages=tuple(args.stages))
            db.close()

        print(json.dumps(report))
        return 0

    except LockUnavailable as e:
        logger.error(f"could not acquire lock: {e}")
        print(json.dumps({'error': 'lock_unavailable', 'detail': str(e)}))
        return 1


def cmd_status(args) -> int:
    cfg = load_config(args.config)
    db = open_db(cfg, allow_replica=args.i_know_this_is_a_replica)
    con = db.conn
    budget = cfg['quota']['daily_budget']
    governor = QuotaGovernor(con, budget)

    day = pacific_day()
    print(f"Quota (Pacific day {day})")
    print("-" * 56)
    spend = governor.spend_by_endpoint(day)
    if spend:
        for endpoint, s in spend.items():
            print(f"  {endpoint:<20} {s['calls']:>8,} calls  {s['units']:>10,} units")
    else:
        print("  no calls recorded today")
    print(f"  {'TOTAL':<20} {'':>8}        {governor.spent_today():>10,} units "
          f"of {budget:,} ({governor.remaining():,} left)")

    print("\nChannels by tier and status")
    print("-" * 56)
    rows = con.execute("""
        SELECT COALESCE(tier, 0) AS tier, COALESCE(status, 'unknown') AS status,
               COUNT(*) AS n
          FROM channels GROUP BY tier, status ORDER BY tier, status
    """).fetchall()
    if rows:
        for tier, status, n in rows:
            print(f"  tier {tier}  {status:<14} {n:>8,}")
    else:
        print("  no channels")

    print("\nSnapshots")
    print("-" * 56)
    for table in ('channel_snapshots', 'video_snapshots'):
        n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        days = con.execute(
            f"SELECT COUNT(DISTINCT substr(observed_at, 1, 10)) FROM {table}"
        ).fetchone()[0]
        print(f"  {table:<20} {n:>10,} rows over {days} day(s)")

    _print_storage(con)

    print("\nLast run")
    print("-" * 56)
    last = con.execute("""
        SELECT run_id, MAX(finished_at) AS finished
          FROM run_log WHERE finished_at IS NOT NULL
         GROUP BY run_id ORDER BY finished DESC LIMIT 1
    """).fetchone()
    if last and last[1]:
        from datetime import datetime
        age = utcnow_dt() - datetime.fromisoformat(last[1])
        hours = age.total_seconds() / 3600
        print(f"  run {last[0]} finished {last[1]} ({hours:.1f}h ago)")
        for r in con.execute("""
            SELECT stage, calls, units_spent, items, note
              FROM run_log WHERE run_id = ? ORDER BY started_at
        """, (last[0],)):
            print(f"    {r[0]:<18} {r[1]:>6,} calls {r[2]:>8,} units "
                  f"{r[3]:>9,} items   {r[4] or ''}")
    else:
        print("  no completed run recorded")

    db.close()
    return 0


def _print_storage(con) -> None:
    """
    Last 7 days of storage_ledger with day-over-day deltas and a projection.

    The NAS is a shared resource, so its growth is measured rather than
    assumed: a linear projection from the observed daily delta is crude but it
    answers the only question the share's owner will ask.
    """
    try:
        rows = con.execute("""
            SELECT day, location, bytes FROM storage_ledger
             WHERE day >= date('now', '-7 day')
             ORDER BY location, day
        """).fetchall()
    except Exception:
        return
    if not rows:
        return

    print("\nStorage (last 7 days)")
    print("-" * 66)
    by_location = {}
    for day, location, byte_count in rows:
        by_location.setdefault(location, []).append((day, byte_count or 0))

    for location, series in by_location.items():
        print(f"  {location}")
        previous = None
        for day, byte_count in series:
            delta = '' if previous is None else f"{(byte_count - previous) / 1e6:+9.1f} MB"
            print(f"    {day}  {byte_count / 1e9:>8.3f} GB  {delta}")
            previous = byte_count
        if len(series) >= 2:
            span_days = len(series) - 1
            per_day = (series[-1][1] - series[0][1]) / span_days
            current = series[-1][1]
            projection = "  ".join(
                f"{n}d {(current + per_day * n) / 1e9:.2f} GB"
                for n in (30, 90, 365))
            print(f"    growth {per_day / 1e6:+.1f} MB/day  ->  {projection}")
        else:
            print("    (one observation; no growth estimate yet)")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Daily YouTube monitoring run')
    sub = parser.add_subparsers(dest='command', required=True)

    p_run = sub.add_parser('run', help='Execute the daily stages')
    p_run.add_argument('--config', default=DEFAULT_CONFIG)
    p_run.add_argument('--stages', nargs='+', default=list(stages.DEFAULT_STAGES),
                       choices=list(stages.STAGES),
                       help='Stages to run, in order')
    p_run.add_argument('--budget', type=int, default=None,
                       help='Override quota.daily_budget for this run')
    p_run.add_argument('--max-tier', type=int, default=None,
                       help='Only serve channels at or below this tier '
                            '(tier 3 is never collected regardless)')
    p_run.add_argument('--i-know-this-is-a-replica', action='store_true',
                       help='Operate on a *.replica.db file. Production is on the cluster.')
    p_run.set_defaults(func=cmd_run)

    p_status = sub.add_parser('status', help='Print quota, tiers, and last run')
    p_status.add_argument('--config', default=DEFAULT_CONFIG)
    p_status.add_argument('--i-know-this-is-a-replica', action='store_true',
                       help='Operate on a *.replica.db file. Production is on the cluster.')
    p_status.set_defaults(func=cmd_status)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ReplicaRefused as e:
        # A policy refusal, not a crash: print it as such so an operator does
        # not read a stack trace as a broken install.
        print(f"Refusing to open the database:\n{e}", file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
