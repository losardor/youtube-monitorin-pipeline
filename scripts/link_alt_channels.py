#!/usr/bin/env python3
"""
2.4 — resolve Wikidata items that map to several YouTube channels.

934 items in the candidate pool carry more than one P2397 value. Each such
group is one organisation or person with several channels: a main channel plus
a clips channel, a regional edition, a second-language feed. Left alone they
would be counted as separate frame members and collected in parallel.

For each group the canonical channel is the one whose title best matches the
Wikidata label by non-stopword token overlap, with `videoCount` as the
tie-breaker and `channel_id` as a final deterministic fallback. Sitelink count
is not used: it is a fame proxy, admissible only as a tie-breaker, and token
overlap plus video count already decide every case here.

The others get `alt_of = <canonical channel_id>` and the canonical row's tier,
so a group is treated consistently. They are collected only when that tier is
0 or 1; at tier 2 an alternate is recorded but not collected, which keeps the
comment budget on the main channel.

Spends no quota: titles and video counts come from the archived channels.list
responses.
"""

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.tier_frame import tokens, qids_of, load_candidates  # noqa: E402

COLLECTABLE_ALT_TIERS = (0, 1)

# An alternate inherits its canonical's tier, but never tier 0. Tier 0 is
# defined as the validated NewsGuard frame -- exactly the channels that passed
# validation on their own merits -- and admitting a channel to it on Wikidata
# provenance alone would quietly redefine the primary frame and break every
# count that rests on it. The brief says "the same tier"; capping at 1 honours
# the intent (an alternate of a tier-0 channel is still collected, since
# collection covers tiers 0-1) without corrupting the frame.
MIN_ALT_TIER = 1


def canonical_of(group, details, label):
    """
    Pick the canonical channel for one Wikidata item.

    Order: token overlap with the label, then videoCount, then channel_id so
    the outcome never depends on dict ordering.
    """
    wanted = tokens(label)

    def key(cid):
        item = details.get(cid, {})
        title = item.get('snippet', {}).get('title', '')
        overlap = len(wanted & tokens(title)) if wanted else 0
        videos = int(item.get('statistics', {}).get('videoCount') or 0)
        return (-overlap, -videos, cid)

    return sorted(group, key=key)[0]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument('--db', default='data/youtube_monitoring.db')
    parser.add_argument('--candidates', default='seeds/wikidata/frame_candidates.csv')
    parser.add_argument('--raw-dir', default='data/raw/wikidata_confirm')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)

    rows = load_candidates(args.candidates)
    raw_dir = Path(args.raw_dir)

    details = {}
    for path in raw_dir.glob('*_[0-9]*.json'):
        for item in json.loads(path.read_text()).get('items', []):
            details[item['id']] = item

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    known = {r['channel_id']: r for r in con.execute(
        "SELECT channel_id, tier, tier_reason FROM channels")}

    # Group channels by Wikidata item, keeping only channels we actually hold.
    by_item, labels = defaultdict(set), {}
    for row in rows:
        cid = row['channel_id']
        if cid not in known:
            continue
        for qid in qids_of(row):
            by_item[qid].add(cid)
            labels.setdefault(qid, row.get('label') or '')

    groups = {q: sorted(c) for q, c in by_item.items() if len(c) > 1}
    print(f"Wikidata items with >1 channel in the database: {len(groups):,}")

    updates, tier_moves, skipped_tier0 = [], [], 0
    for qid, group in sorted(groups.items()):
        canonical = canonical_of(group, details, labels.get(qid, ''))
        for cid in group:
            if cid == canonical:
                continue
            # Tier 0 is the validated NewsGuard frame and is never restructured
            # by Wikidata provenance: those channels were validated on their
            # own merits.
            if known[cid]['tier'] == 0:
                skipped_tier0 += 1
                continue
            updates.append((canonical, cid))
            canon_tier = max(known[canonical]['tier'], MIN_ALT_TIER)
            if known[cid]['tier'] != canon_tier:
                reason = (known[canonical]['tier_reason'] or 'canonical') + ':alt'
                tier_moves.append((canon_tier, reason, cid))

    print(f"alternates to link:                          {len(updates):,}")
    print(f"  of which retiered to match their canonical {len(tier_moves):,}")
    print(f"tier-0 channels left alone:                  {skipped_tier0:,}")

    if args.dry_run:
        con.close()
        return 0

    con.executemany("UPDATE channels SET alt_of = ? WHERE channel_id = ?", updates)
    con.executemany(
        "UPDATE channels SET tier = ?, tier_reason = ? WHERE channel_id = ?",
        tier_moves)
    con.commit()

    linked = con.execute(
        "SELECT COUNT(*) FROM channels WHERE alt_of IS NOT NULL").fetchone()[0]
    collectable = con.execute(
        "SELECT COUNT(*) FROM channels WHERE alt_of IS NOT NULL AND tier <= 1"
    ).fetchone()[0]
    print(f"\nchannels with alt_of set: {linked:,} "
          f"({collectable:,} at tier 0-1, so actually collected)")
    print("tier distribution:")
    for r in con.execute("SELECT tier, COUNT(*) FROM channels GROUP BY tier ORDER BY tier"):
        print(f"  tier {r[0]}: {r[1]:,}")
    con.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
