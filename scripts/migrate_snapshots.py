#!/usr/bin/env python3
"""
Backfill observation number one of the snapshot series.

The existing database holds a single point-in-time collection: the latest
observed statistics live in columns on `channels` and `videos`, with no record
of when the series started. Adding the snapshot tables without a backfill would
make that collection a gap rather than a first data point, so this script
copies each existing record into `channel_snapshots` / `video_snapshots` with
`observed_at` taken from the record's own collection timestamp.

Sources of observed_at:
  channels -> COALESCE(first_collected_at, last_updated_at)
              (first_collected_at was never populated before this migration;
               last_updated_at is what the Nov 2025 runs actually wrote)
  videos   -> collected_at

NULLs are preserved as NULL, never coerced to 0: a video with comments
disabled has no comment count, which is not the same as a count of zero.

Idempotent: the snapshot tables are keyed by (id, observed_at) and the
timestamps come from the records themselves, so a second run inserts nothing.

The database is never defaulted -- --db is required, so this cannot be pointed
at the live file by accident.
"""

import argparse
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.database import Database  # noqa: E402


def counts(con: sqlite3.Connection) -> dict:
    """Row counts for the tables this migration touches."""
    out = {}
    for table in ('channels', 'videos', 'channel_snapshots', 'video_snapshots'):
        try:
            out[table] = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        except sqlite3.OperationalError:
            out[table] = None
    return out


def backfill(con: sqlite3.Connection) -> dict:
    """
    Insert one snapshot row per existing channel and video.

    Returns a dict of rows inserted per table.
    """
    cur = con.cursor()

    # hidden_subscribers has no equivalent column on `channels`, so the
    # backfilled row leaves it NULL; it is populated from
    # statistics.hiddenSubscriberCount on subsequent observations only.
    cur.execute("""
        INSERT OR IGNORE INTO channel_snapshots (
            channel_id, observed_at, subscriber_count,
            hidden_subscribers, view_count, video_count
        )
        SELECT channel_id,
               COALESCE(first_collected_at, last_updated_at),
               subscriber_count,
               NULL,
               view_count,
               video_count
        FROM channels
        WHERE COALESCE(first_collected_at, last_updated_at) IS NOT NULL
    """)
    channels_inserted = cur.rowcount

    cur.execute("""
        INSERT OR IGNORE INTO video_snapshots (
            video_id, observed_at, view_count, like_count, comment_count
        )
        SELECT video_id, collected_at, view_count, like_count, comment_count
        FROM videos
        WHERE collected_at IS NOT NULL
    """)
    videos_inserted = cur.rowcount

    con.commit()
    return {
        'channel_snapshots': channels_inserted,
        'video_snapshots': videos_inserted,
    }


def skipped(con: sqlite3.Connection) -> dict:
    """Records that could not be backfilled because they carry no timestamp."""
    return {
        'channels': con.execute(
            "SELECT COUNT(*) FROM channels "
            "WHERE COALESCE(first_collected_at, last_updated_at) IS NULL"
        ).fetchone()[0],
        'videos': con.execute(
            "SELECT COUNT(*) FROM videos WHERE collected_at IS NULL"
        ).fetchone()[0],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description='Backfill channel_snapshots and video_snapshots from '
                    'existing records. Idempotent.'
    )
    parser.add_argument(
        '--db', required=True,
        help='Path to the SQLite database. Required: run this on a copy first.'
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Report what would be inserted without writing.'
    )
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.exists():
        parser.error(f"database not found: {db_path}")

    print(f"Database: {db_path}")

    # Opening through Database applies the schema additions (new tables and
    # guarded ALTERs) before the backfill runs, so a single invocation of this
    # script migrates an old file end to end.
    db = Database(db_path=str(db_path))
    con = db.conn

    before = counts(con)
    print("\nBefore:")
    for table, n in before.items():
        print(f"  {table:<20} {n:>10,}")

    missing = skipped(con)
    if missing['channels'] or missing['videos']:
        print("\nNo timestamp, will be skipped:")
        print(f"  channels {missing['channels']:,}, videos {missing['videos']:,}")

    if args.dry_run:
        pending_c = con.execute("""
            SELECT COUNT(*) FROM channels c
            WHERE COALESCE(c.first_collected_at, c.last_updated_at) IS NOT NULL
              AND NOT EXISTS (
                SELECT 1 FROM channel_snapshots s
                WHERE s.channel_id = c.channel_id
                  AND s.observed_at = COALESCE(c.first_collected_at, c.last_updated_at)
              )
        """).fetchone()[0]
        pending_v = con.execute("""
            SELECT COUNT(*) FROM videos v
            WHERE v.collected_at IS NOT NULL
              AND NOT EXISTS (
                SELECT 1 FROM video_snapshots s
                WHERE s.video_id = v.video_id AND s.observed_at = v.collected_at
              )
        """).fetchone()[0]
        print(f"\nDry run: would insert {pending_c:,} channel and "
              f"{pending_v:,} video snapshot rows.")
        db.close()
        return 0

    inserted = backfill(con)
    after = counts(con)

    print("\nInserted:")
    for table, n in inserted.items():
        print(f"  {table:<20} {n:>10,}")

    print("\nAfter:")
    for table, n in after.items():
        print(f"  {table:<20} {n:>10,}")

    ok = (after['channel_snapshots'] >= before['channels'] - missing['channels']
          and after['video_snapshots'] >= before['videos'] - missing['videos'])
    print("\n" + ("Backfill complete." if ok else "WARNING: fewer snapshots than records."))

    db.close()
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
