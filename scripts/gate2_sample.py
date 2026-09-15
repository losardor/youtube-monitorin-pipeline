#!/usr/bin/env python3
"""
Draw the Gate 2 hand-check sample, stratified by admitting check.

Four strata of 25: tier-1 outlets admitted on 'topic', tier-1 outlets admitted
on 'title_only', and the same split for tier-2 individuals. Reporting a
false-positive rate per stratum as well as pooled is what makes a failure
actionable: if only title_only fails, that stratum is demoted with an UPDATE
on tier_reason and no quota is spent.

'topic+title' rows are pooled into the 'topic' stratum -- they passed the topic
check, the title agreeing as well does not make them a different kind of row.

Output is a CSV for hand-checking with a blank `verdict` column, plus enough
context (channel title, seed label, topics, subscriber count, URL) to judge
each row without opening the API.
"""

import argparse
import csv
import json
import random
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

STRATA = [
    ('tier1_topic', 1, ('topic', 'topic+title')),
    ('tier1_title_only', 1, ('title_only',)),
    ('tier2_topic', 2, ('topic', 'topic+title')),
    ('tier2_title_only', 2, ('title_only',)),
]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument('--db', default='data/youtube_monitoring.db')
    parser.add_argument('--raw-dir', default='data/raw/wikidata_confirm')
    parser.add_argument('--out', default='data/gate2_sample.csv')
    parser.add_argument('--per-stratum', type=int, default=25)
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args(argv)

    raw_dir = Path(args.raw_dir)
    meta = json.loads((raw_dir / 'confirm_meta.json').read_text())

    # Channel details from the archived responses: no quota, no second call.
    details = {}
    for path in raw_dir.glob('*_[0-9]*.json'):
        for item in json.loads(path.read_text()).get('items', []):
            details[item['id']] = item

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    random.seed(args.seed)

    rows = []
    for name, tier, reasons in STRATA:
        placeholders = ','.join('?' * len(reasons))
        pool = con.execute(
            f"SELECT channel_id, tier, tier_reason FROM channels "
            f"WHERE tier = ? AND tier_reason IN ({placeholders}) "
            f"ORDER BY channel_id", (tier, *reasons)).fetchall()
        if not pool:
            print(f"{name:<20} EMPTY -- nothing to sample")
            continue
        take = min(args.per_stratum, len(pool))
        picked = random.sample(list(pool), take)
        print(f"{name:<20} pool {len(pool):>6,}  sampled {take}")

        for r in picked:
            cid = r['channel_id']
            item = details.get(cid, {})
            snippet = item.get('snippet', {})
            stats = item.get('statistics', {})
            topics = [u.rstrip('/').rsplit('/', 1)[-1]
                      for u in item.get('topicDetails', {}).get('topicCategories', [])]
            rows.append({
                'stratum': name,
                'tier': r['tier'],
                'tier_reason': r['tier_reason'],
                'channel_id': cid,
                'channel_title': snippet.get('title', ''),
                'seed_label': meta.get(cid, {}).get('label', ''),
                'wd_class': meta.get(cid, {}).get('wd_class', ''),
                'country': snippet.get('country', ''),
                'subscribers': stats.get('subscriberCount', ''),
                'videos': stats.get('videoCount', ''),
                'topics': '|'.join(topics),
                'url': f"https://www.youtube.com/channel/{cid}",
                'description': (snippet.get('description', '') or '')[:180].replace('\n', ' '),
                'verdict': '',          # 'ok' or 'false_positive'
                'note': '',
            })

    out = Path(args.out)
    with open(out, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nWrote {out}: {len(rows)} rows for hand-checking "
          f"(fill the `verdict` column with ok / false_positive)")
    con.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
