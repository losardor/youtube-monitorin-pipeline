#!/usr/bin/env python3
"""
Load the validation-phase statistics into channel_snapshots as real observations.

Each successful entry in validation_progress.json recorded a subscriber count
and a video count at a known instant -- the moment that URL was validated,
between December 2025 and April 2026. Those are genuine observations of the
channel, made months before the monitoring series starts, and discarding them
would throw away a free earlier data point.

What is written:
  observed_at        the entry's validated_at
  subscriber_count   as recorded
  video_count        as recorded
  view_count         NULL -- the validator never recorded it
  hidden_subscribers NULL -- likewise

view_count is left NULL rather than 0: the validator did not observe it, which
is not the same as observing zero.

A channel validated from two URLs on two dates yields two observations, which
is correct -- they are two separate looks at the same channel.

Spends no quota. Idempotent: (channel_id, observed_at) is the primary key.
"""

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.database import Database  # noqa: E402


def as_int(value):
    """Validator fields arrive as strings; absence must stay None, not 0."""
    if value in (None, '', 'None'):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def observations(validation_path: str) -> list:
    with open(validation_path) as f:
        results = json.load(f)['results']

    rows, skipped = [], 0
    for entry in results:
        if entry.get('success') not in (True, 'True'):
            continue
        cid = entry.get('channel_id')
        observed_at = entry.get('validated_at')
        if not cid or not observed_at:
            skipped += 1
            continue
        subs = as_int(entry.get('subscriber_count'))
        vids = as_int(entry.get('video_count'))
        if subs is None and vids is None:
            skipped += 1        # nothing observed, nothing to record
            continue
        rows.append((cid, observed_at, subs, vids))
    return rows, skipped


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument('--db', required=True)
    parser.add_argument('--validation', default='data/validation/validation_progress.json')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)

    rows, skipped = observations(args.validation)
    db = Database(db_path=args.db)
    con = db.conn

    known = {r[0] for r in con.execute("SELECT channel_id FROM channels")}
    # A snapshot without a parent channel row would be an orphan observation.
    usable = [r for r in rows if r[0] in known]
    orphaned = len(rows) - len(usable)

    before = con.execute("SELECT COUNT(*) FROM channel_snapshots").fetchone()[0]
    print(f"Validation entries with statistics: {len(rows):>8,}")
    print(f"  skipped (no id/date/stats):       {skipped:>8,}")
    print(f"  no matching channel row:          {orphaned:>8,}")
    print(f"  usable:                           {len(usable):>8,}")

    if args.dry_run:
        db.close()
        return 0

    con.executemany("""
        INSERT OR IGNORE INTO channel_snapshots (
            channel_id, observed_at, subscriber_count,
            hidden_subscribers, view_count, video_count
        ) VALUES (?, ?, ?, NULL, NULL, ?)
    """, [(cid, at, subs, vids) for cid, at, subs, vids in usable])
    con.commit()

    after = con.execute("SELECT COUNT(*) FROM channel_snapshots").fetchone()[0]
    span = con.execute("""
        SELECT MIN(observed_at), MAX(observed_at), COUNT(*)
          FROM channel_snapshots WHERE view_count IS NULL
    """).fetchone()
    distinct_channels = con.execute(
        "SELECT COUNT(DISTINCT channel_id) FROM channel_snapshots").fetchone()[0]
    multi = con.execute("""
        SELECT COUNT(*) FROM (
            SELECT channel_id FROM channel_snapshots
             GROUP BY channel_id HAVING COUNT(*) > 1)
    """).fetchone()[0]

    print(f"\nchannel_snapshots: {before:,} -> {after:,}  (+{after - before:,})")
    print(f"observed_at range (validation rows): {span[0]} .. {span[1]}")
    print(f"distinct channels with >=1 observation: {distinct_channels:,}")
    print(f"channels with more than one observation: {multi:,}")

    db.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
