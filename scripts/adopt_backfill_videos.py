#!/usr/bin/env python3
"""
Adopt pre-daily-pipeline videos into the comment queue.

Videos collected by collect.py before the monitoring core existed carry
comments_state NULL. The comment queue matches only 'pending' or 'done', so
those videos are invisible to it: their comments would never be harvested and
never re-polled, silently and without an error anywhere.

Adoption:

  already have comment rows  -> 'done', last_comment_count set from the video's
                                current comment_count, so the growth re-poll
                                has a baseline to compare against
  no comment rows            -> 'pending', so the next run harvests them

Spends no quota. Idempotent: only rows with a NULL state are touched.
"""

import argparse
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument('--db', required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)

    con = sqlite3.connect(args.db)
    q = lambda sql: con.execute(sql).fetchone()[0]  # noqa: E731

    total = q("SELECT COUNT(*) FROM videos WHERE comments_state IS NULL")
    with_comments = q("""
        SELECT COUNT(*) FROM videos v WHERE v.comments_state IS NULL
          AND EXISTS (SELECT 1 FROM comments c WHERE c.video_id = v.video_id)
    """)
    without = total - with_comments
    claimed = q("""
        SELECT COUNT(*) FROM videos v WHERE v.comments_state IS NULL
          AND COALESCE(v.comment_count, 0) > 0
          AND NOT EXISTS (SELECT 1 FROM comments c WHERE c.video_id = v.video_id)
    """)

    print(f"videos with NULL comments_state:      {total:>8,}")
    print(f"  have comment rows      -> 'done'    {with_comments:>8,}")
    print(f"  no comment rows        -> 'pending' {without:>8,}")
    print(f"    of which claim comment_count > 0: {claimed:>8,}"
          "   <- collected before the truncation fix, or never reached")

    if args.dry_run:
        con.close()
        return 0

    con.execute("""
        UPDATE videos
           SET comments_state = 'done',
               last_comment_count = COALESCE(last_comment_count, comment_count)
         WHERE comments_state IS NULL
           AND EXISTS (SELECT 1 FROM comments c WHERE c.video_id = videos.video_id)
    """)
    con.execute("""
        UPDATE videos SET comments_state = 'pending'
         WHERE comments_state IS NULL
    """)
    con.commit()

    print("\nafter:")
    for state, n in con.execute(
            "SELECT COALESCE(comments_state, '(null)'), COUNT(*) FROM videos "
            "GROUP BY comments_state ORDER BY 2 DESC"):
        print(f"  {state:<12} {n:>8,}")
    remaining = q("SELECT COUNT(*) FROM videos WHERE comments_state IS NULL")
    print(f"\nstill NULL: {remaining}")
    con.close()
    return 0 if remaining == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
