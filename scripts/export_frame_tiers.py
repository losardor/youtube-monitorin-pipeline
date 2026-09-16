#!/usr/bin/env python3
"""
2.x — export data/frame_tiers.csv, the frame's tier assignment as a flat file.

Columns as specified in the brief: channel_id, tier, wd_item, wd_class, label,
country, reason. Plus alt_of, because a reader needs to know that a row is an
alternate of another channel rather than an independent frame member.

The `reason` column is the audit trail. It accumulates suffixes, so a value
reads as the history of the decision:

  topic+title                     admitted on both checks, active
  topic:stale                     topic-matched, no upload in 180 days
  title_only:gate2_fp68           dropped: its stratum measured 68% FP
  topic:politics                  individual kept by the rule-(a) tightening
  topic+title:no_politics         individual dropped by that tightening
  ...:country_from_citizenship    country is P27, not the channel's own
  ...:alt                         alternate of a canonical channel

Spends no quota.
"""

import argparse
import csv
import json
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.tier_frame import load_candidates  # noqa: E402

FIELDS = ['channel_id', 'tier', 'wd_item', 'wd_class', 'label', 'country',
          'reason', 'alt_of']


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument('--db', default='data/youtube_monitoring.db')
    parser.add_argument('--candidates', default='seeds/wikidata/frame_candidates.csv')
    parser.add_argument('--raw-dir', default='data/raw/wikidata_confirm')
    parser.add_argument('--out', default='data/frame_tiers.csv')
    args = parser.parse_args(argv)

    seeds = {}
    for row in load_candidates(args.candidates):
        seeds.setdefault(row['channel_id'], row)

    # Channel titles from the archive, for rows with no Wikidata label.
    titles = {}
    raw_dir = Path(args.raw_dir)
    for path in raw_dir.glob('*_[0-9]*.json'):
        for item in json.loads(path.read_text()).get('items', []):
            titles[item['id']] = item.get('snippet', {}).get('title', '')

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    rows = con.execute("""
        SELECT channel_id, tier, tier_reason, wd_item, wd_class, country,
               channel_title, source_domain, alt_of
          FROM channels
         ORDER BY tier, channel_id
    """).fetchall()

    out_rows = []
    for r in rows:
        cid = r['channel_id']
        seed = seeds.get(cid, {})
        out_rows.append({
            'channel_id': cid,
            'tier': r['tier'],
            'wd_item': r['wd_item'] or seed.get('wd_item') or '',
            'wd_class': r['wd_class'] or seed.get('wd_class') or '',
            # Prefer the channel's own title; fall back to the seed label, then
            # the archived title. A bare QID as a label is not a name.
            'label': (r['channel_title'] or seed.get('label')
                      or titles.get(cid) or ''),
            'country': r['country'] or seed.get('country') or '',
            'reason': r['tier_reason'] or ('newsguard_validated'
                                           if r['tier'] == 0 else ''),
            'alt_of': r['alt_of'] or '',
        })

    out = Path(args.out)
    with open(out, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(out_rows)

    print(f"Wrote {out}: {len(out_rows):,} rows")
    from collections import Counter
    print("\ntier   rows   distinct reasons")
    by_tier = Counter(r['tier'] for r in out_rows)
    for tier in sorted(by_tier):
        reasons = len({r['reason'] for r in out_rows if r['tier'] == tier})
        print(f"  {tier}  {by_tier[tier]:>6,}   {reasons:>3}")
    missing = sum(1 for r in out_rows if not r['label'])
    print(f"\nrows with no usable label: {missing:,}")
    con.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
