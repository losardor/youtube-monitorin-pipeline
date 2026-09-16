#!/usr/bin/env python3
"""
Load the validated NewsGuard frame into `channels` as tier 0.

Source: data/validation/validation_progress.json, the authoritative record of
the validation phase (3,307 URLs, 2,867 successes, 2,856 distinct channel ids
after duplicates). Each id is joined back to data/sources.csv via the URL it
was validated from, to carry source_domain / source_rating / source_orientation.

Spends no quota. Nothing here calls the API: channel statistics and
uploads_playlist arrive from the first `daily.py run --stages channels` pass.
Statistics observed during the validation phase are loaded separately by
scripts/backfill_validation_snapshots.py, so for most channels the daily pass
is the *next* observation rather than the first.

Existing rows are preserved. The 29 channels already collected in November 2025
keep their statistics, their snapshots and their collection timestamps; this
script only fills in tier and the source metadata for them. Channels already in
the database but absent from the validated set are marked tier 3 and keep their
data -- they are recorded, not collected, and never deleted.

Idempotent: re-running changes nothing that is already correct.
"""

import argparse
import csv
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.database import Database  # noqa: E402

VALIDATION = 'data/validation/validation_progress.json'
SOURCES = 'data/sources.csv'

TIER_PRIMARY = 0     # validated NewsGuard frame
TIER_RECORDED = 3    # in the database, not in the frame: keep, never collect


def load_validated(path: str) -> list:
    """Successful validation entries carrying a channel id."""
    with open(path) as f:
        payload = json.load(f)
    return [r for r in payload['results']
            if r.get('success') in (True, 'True') and r.get('channel_id')]


def load_sources(path: str) -> dict:
    """Map YouTube URL -> source row, for the NewsGuard metadata columns."""
    csv.field_size_limit(sys.maxsize)
    by_url = {}
    with open(path) as f:
        for row in csv.DictReader(f):
            url = (row.get('Youtube') or '').strip()
            if url:
                by_url.setdefault(url, row)
    return by_url


def build_frame(validated: list, sources: dict) -> tuple:
    """
    Collapse validation entries to one row per channel id.

    A channel referenced from several source rows keeps the earliest-validated
    entry, deterministically, and the collision is reported rather than hidden:
    the others are the same channel reached from a different outlet URL.
    """
    by_channel = defaultdict(list)
    for entry in validated:
        by_channel[entry['channel_id']].append(entry)

    frame, collisions = {}, {}
    for cid, entries in by_channel.items():
        entries.sort(key=lambda e: (e.get('validated_at') or '', e.get('url') or ''))
        chosen = entries[0]
        if len(entries) > 1:
            collisions[cid] = [e.get('url') for e in entries]

        src = sources.get(chosen.get('url'), {})
        frame[cid] = {
            'channel_id': cid,
            'channel_url': f"https://www.youtube.com/channel/{cid}",
            'source_domain': src.get('Domain') or chosen.get('domain'),
            'source_rating': src.get('Rating'),
            'source_orientation': src.get('Orientation'),
        }
    return frame, collisions


def apply_frame(con: sqlite3.Connection, frame: dict, dry_run: bool = False) -> dict:
    """Upsert the frame, preserving everything already collected."""
    existing = {r[0] for r in con.execute("SELECT channel_id FROM channels")}
    to_insert = [c for c in frame if c not in existing]
    to_update = [c for c in frame if c in existing]
    recorded_only = sorted(existing - set(frame))

    stats = {
        'frame_size': len(frame),
        'inserted': len(to_insert),
        'updated_in_place': len(to_update),
        'recorded_not_in_frame': len(recorded_only),
        'recorded_ids': recorded_only,
    }
    if dry_run:
        return stats

    # New channels: identity and provenance only. Statistics stay NULL so that
    # no latest-observed value exists without a matching snapshot row. The
    # series itself starts earlier, from the validation-phase observations.
    con.executemany("""
        INSERT INTO channels (
            channel_id, channel_url, source_domain, source_rating,
            source_orientation, tier, status, last_checked
        ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL)
    """, [(frame[c]['channel_id'], frame[c]['channel_url'],
           frame[c]['source_domain'], frame[c]['source_rating'],
           frame[c]['source_orientation'], TIER_PRIMARY) for c in to_insert])

    # Existing channels: fill tier and source metadata, touch nothing else.
    # COALESCE keeps any source metadata already recorded by collect.py.
    con.executemany("""
        UPDATE channels
           SET tier = ?,
               source_domain = COALESCE(source_domain, ?),
               source_rating = COALESCE(source_rating, ?),
               source_orientation = COALESCE(source_orientation, ?)
         WHERE channel_id = ?
    """, [(TIER_PRIMARY, frame[c]['source_domain'], frame[c]['source_rating'],
           frame[c]['source_orientation'], c) for c in to_update])

    # In the database, not in the frame: keep the data, never collect it.
    if recorded_only:
        con.executemany(
            "UPDATE channels SET tier = ? WHERE channel_id = ?",
            [(TIER_RECORDED, c) for c in recorded_only])

    con.commit()
    return stats


def verify(con: sqlite3.Connection) -> dict:
    """Post-conditions worth asserting before this is called done."""
    q = lambda sql: con.execute(sql).fetchone()[0]  # noqa: E731
    return {
        'channels_total': q("SELECT COUNT(*) FROM channels"),
        'tier_0': q("SELECT COUNT(*) FROM channels WHERE tier = 0"),
        'tier_3': q("SELECT COUNT(*) FROM channels WHERE tier = 3"),
        'with_rating': q("SELECT COUNT(*) FROM channels WHERE source_rating IS NOT NULL"),
        'videos': q("SELECT COUNT(*) FROM videos"),
        'comments': q("SELECT COUNT(*) FROM comments"),
        'channel_snapshots': q("SELECT COUNT(*) FROM channel_snapshots"),
        'video_snapshots': q("SELECT COUNT(*) FROM video_snapshots"),
        'orphan_videos': q("SELECT COUNT(*) FROM videos v WHERE NOT EXISTS "
                           "(SELECT 1 FROM channels c WHERE c.channel_id = v.channel_id)"),
        'stats_without_snapshot': q("""
            SELECT COUNT(*) FROM channels c
             WHERE c.subscriber_count IS NOT NULL
               AND NOT EXISTS (SELECT 1 FROM channel_snapshots s
                               WHERE s.channel_id = c.channel_id)
        """),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument('--db', required=True,
                        help='Target database. Run on a copy first.')
    parser.add_argument('--validation', default=VALIDATION)
    parser.add_argument('--sources', default=SOURCES)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)

    validated = load_validated(args.validation)
    sources = load_sources(args.sources)
    frame, collisions = build_frame(validated, sources)

    print(f"Validated successes:      {len(validated):>8,}")
    print(f"Distinct channel ids:     {len(frame):>8,}")
    print(f"Ids from several URLs:    {len(collisions):>8,}")
    missing_rating = sum(1 for v in frame.values() if not v['source_rating'])
    print(f"No NewsGuard rating:      {missing_rating:>8,}")

    db = Database(db_path=args.db)
    before = verify(db.conn)

    stats = apply_frame(db.conn, frame, dry_run=args.dry_run)
    print(f"\n{'Would insert' if args.dry_run else 'Inserted'}:"
          f"          {stats['inserted']:>8,}")
    print(f"Updated in place:         {stats['updated_in_place']:>8,}")
    print(f"Recorded, not in frame:   {stats['recorded_not_in_frame']:>8,}"
          f"  {stats['recorded_ids']}")

    if args.dry_run:
        db.close()
        return 0

    after = verify(db.conn)
    print("\n{:<26} {:>12} {:>12}".format('', 'before', 'after'))
    for key in after:
        if key == 'recorded_ids':
            continue
        print(f"{key:<26} {before[key]:>12,} {after[key]:>12,}")

    ok = (after['tier_0'] == len(frame)
          and after['videos'] == before['videos']
          and after['comments'] == before['comments']
          and after['channel_snapshots'] == before['channel_snapshots']
          and after['video_snapshots'] == before['video_snapshots']
          and after['orphan_videos'] == 0
          and after['stats_without_snapshot'] == 0)
    print("\n" + ("Frame loaded; collected data untouched."
                  if ok else "WARNING: post-conditions not met."))
    db.close()
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
