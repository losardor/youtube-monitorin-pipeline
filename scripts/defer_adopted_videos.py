#!/usr/bin/env python3
"""
Park the pre-daily-pipeline videos as `deferred`. One-off, no quota.

4,305 videos collected by collect.py before the monitoring core existed were
adopted as `pending` on 2026-09-16 so they would not be invisible. Three cron
runs later none had been harvested, and none ever would be: the queue orders
by publication date, and ~52,000 newer videos sit permanently ahead of them.
Leaving them `pending` makes the backlog look 4,305 larger than the work the
pipeline will actually do.

`deferred` records the decision instead of hiding it -- these videos are known,
countable, and collectable later by an explicit choice, rather than quietly
starved.

The cutover instant is the boundary: anything collected before it came from the
backfill, anything after from the daily pipeline.
"""

import argparse
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

CUTOVER = '2026-09-16T10:47:44'


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument('--db', required=True)
    parser.add_argument('--cutover', default=CUTOVER,
                        help='Videos collected before this instant are backfill')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row

    rows = con.execute("""
        SELECT COUNT(*) AS n,
               MIN(published_at) AS oldest,
               MAX(published_at) AS newest,
               SUM(COALESCE(comment_count, 0)) AS comments_claimed
          FROM videos
         WHERE comments_state = 'pending' AND collected_at < ?
    """, (args.cutover,)).fetchone()

    print(f"pending videos collected before {args.cutover}: {rows['n']:,}")
    print(f"  published {rows['oldest']} .. {rows['newest']}")
    print(f"  comments claimed by their metadata: {rows['comments_claimed'] or 0:,}")

    if args.dry_run:
        con.close()
        return 0

    cur = con.execute("""
        UPDATE videos SET comments_state = 'deferred'
         WHERE comments_state = 'pending' AND collected_at < ?
    """, (args.cutover,))
    con.commit()
    print(f"\nmarked deferred: {cur.rowcount:,}")

    print("\ncomments_state after:")
    for state, n in con.execute(
            "SELECT COALESCE(comments_state,'(null)'), COUNT(*) FROM videos "
            "GROUP BY comments_state ORDER BY 2 DESC"):
        print(f"  {state:<12} {n:>8,}")
    con.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
