#!/usr/bin/env python3
"""
Re-check channels marked `unresolved`, and separate two different failures.

`unresolved` currently conflates two things:

  - the channel itself is gone (channels.list does not return its id);
  - the channel is alive but its uploads playlist refused a request, which
    discover_uploads also recorded as `unresolved`.

The second is not a dead channel, and treating it as one loses a live channel
from the frame. Worse, `resolve_channels` flips such a row back to `active` on
its next pass, discovery fails on it again, and the pair oscillate forever
spending a unit each time.

This re-checks every unresolved channel with channels.list (1 unit per 50) and,
for those a playlist error marked, re-requests the uploads playlist once
(1 unit each). Outcomes:

  active               resolves and its playlist answers -- back in service
  uploads_unavailable  resolves but the playlist does not; kept out of
                       discovery, and resolve_channels does NOT flip it back
  unresolved           channels.list still does not return it: genuinely gone

SPENDS QUOTA: about 1 + N units, N being the channels needing a playlist probe.
"""

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.database import Database                                   # noqa: E402
from src.errors import QuotaExhausted, ItemUnavailable, APIError     # noqa: E402
from src.quota import QuotaGovernor, DAILY_FORBIDDEN_ENDPOINTS       # noqa: E402
from src.timeutil import utcnow                                      # noqa: E402
from src.youtube_client import YouTubeAPIClient                      # noqa: E402

STATUS_UPLOADS_UNAVAILABLE = 'uploads_unavailable'


def chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument('--db', default='/data/ytmon/youtube_monitoring.db')
    parser.add_argument('--budget', type=int, default=200)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)

    db = Database(db_path=args.db)
    con = db.conn

    rows = con.execute("""
        SELECT channel_id, COALESCE(tier, 0) AS tier, channel_title,
               uploads_playlist, last_checked, source_domain
          FROM channels WHERE status = 'unresolved'
         ORDER BY tier, channel_id
    """).fetchall()

    print(f"unresolved channels: {len(rows)}")
    print(f"{'channel_id':<26} {'tier':>4}  {'has_playlist':<12} marked_by")
    print('-' * 78)
    for r in rows:
        # A channel with an uploads_playlist recorded was resolved at least
        # once, so discovery is what demoted it; one with none never resolved.
        marked_by = 'discovery' if r['uploads_playlist'] else 'channels.list'
        print(f"{r['channel_id']:<26} {r['tier']:>4}  "
              f"{'yes' if r['uploads_playlist'] else 'no':<12} {marked_by}")

    by_discovery = [r for r in rows if r['uploads_playlist']]
    by_lookup = [r for r in rows if not r['uploads_playlist']]
    cost = -(-len(rows) // 50) + len(by_discovery)
    print(f"\nmarked by discovery: {len(by_discovery)}   "
          f"by channels.list: {len(by_lookup)}")
    print(f"estimated cost: {cost} units")

    if args.dry_run:
        db.close()
        return 0

    governor = QuotaGovernor(con, args.budget,
                             forbidden_endpoints=DAILY_FORBIDDEN_ENDPOINTS)
    key = os.environ.get('YOUTUBE_API_KEY')
    if not key:
        raise SystemExit("YOUTUBE_API_KEY not set")
    client = YouTubeAPIClient(api_key=key, governor=governor, allow_search=False)
    spent_before = governor.spent_today()

    # Pass 1: does channels.list return it at all?
    ids = [r['channel_id'] for r in rows]
    returned = {}
    for batch in chunks(ids, 50):
        try:
            page = client.channels_by_id(batch)
        except QuotaExhausted as e:
            print(f"stopped: {e}")
            break
        for item in page.get('items', []):
            returned[item['id']] = item

    gone = [c for c in ids if c not in returned]
    alive = [c for c in ids if c in returned]
    print(f"\npass 1: {len(alive)} resolve, {len(gone)} do not")

    # Pass 2: for the ones discovery demoted, does the playlist answer?
    now = utcnow()
    updates = []
    for r in rows:
        cid = r['channel_id']
        if cid in gone:
            updates.append(('unresolved', now, cid))
            continue
        item = returned[cid]
        playlist = (item.get('contentDetails', {})
                        .get('relatedPlaylists', {}).get('uploads'))
        if not playlist:
            updates.append((STATUS_UPLOADS_UNAVAILABLE, now, cid))
            continue
        try:
            client.playlist_items(playlist)
            updates.append(('active', now, cid))
        except QuotaExhausted as e:
            print(f"stopped in pass 2: {e}")
            break
        except (ItemUnavailable, APIError) as e:
            print(f"  {cid}: playlist refused -- {str(e)[:70]}")
            updates.append((STATUS_UPLOADS_UNAVAILABLE, now, cid))

    con.executemany(
        "UPDATE channels SET status = ?, last_checked = ? WHERE channel_id = ?",
        updates)
    con.commit()

    print(f"\nunits spent: {governor.spent_today() - spent_before}")
    print("\nstatus after:")
    for status, n in con.execute(
            "SELECT COALESCE(status,'(null)'), COUNT(*) FROM channels "
            "WHERE channel_id IN (%s) GROUP BY status ORDER BY 2 DESC"
            % ','.join('?' * len(ids)), ids):
        print(f"  {status:<22} {n:>4}")
    db.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
