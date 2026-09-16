#!/usr/bin/env python3
"""
Apply the tier-2 decisions taken after Gate 2. Spends no quota.

Three changes, each resting on a measured false-positive rate rather than a
guess:

1. **Individuals: rule (a), Politics topic required.** Selected by comparing
   three tightenings against the rows hand-checked at Gate 2, then validated on
   a fresh 50-row draw that came in at 8% against a 15% threshold. Individuals
   that keep a Politics topic stay tier 2 with `:politics` appended to the
   reason; the rest go to tier 3.

2. **Outlets admitted on `title_only` go to tier 3**, whatever the suffix. That
   stratum measured 68% false positives at Gate 2, and the rate is a property
   of the admitting check, not of where the row happens to sit.

3. **Topic-matched stale outlets stay tier 2.** They passed at 0%; being
   dormant is a cost question, not a precision question, and a dormant outlet
   that resumes publishing is itself a finding.

Idempotent: re-running makes no further change, because the reason suffix it
writes is also what it filters on.
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.calibrate_rules import load_raw, evaluate  # noqa: E402

TIER_KEEP = 2
TIER_DROP = 3


def topic_names(record) -> set:
    return {u.rstrip('/').rsplit('/', 1)[-1] for u in record['topics']}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument('--db', default='data/youtube_monitoring.db')
    parser.add_argument('--raw-dir', default='data/raw/wikidata_confirm')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)

    raw_dir = Path(args.raw_dir)
    meta = json.loads((raw_dir / 'confirm_meta.json').read_text())
    items, requested = load_raw(raw_dir, 'person_candidate')
    persons = {r['channel_id']: r for r in evaluate(items, requested, meta)}

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row

    before = {r['tier']: r['n'] for r in con.execute(
        "SELECT tier, COUNT(*) AS n FROM channels GROUP BY tier")}

    rows = con.execute(
        "SELECT channel_id, tier_reason FROM channels WHERE tier = ?",
        (TIER_KEEP,)).fetchall()

    keep_individual, drop_individual = [], []
    keep_outlet, drop_outlet = [], []

    for row in rows:
        cid, reason = row['channel_id'], row['tier_reason'] or ''
        if cid in persons:
            if 'Politics' in topic_names(persons[cid]):
                # Suffix already present means this has run before.
                new = reason if reason.endswith(':politics') else f"{reason}:politics"
                keep_individual.append((new, cid))
            else:
                drop_individual.append((f"{reason}:no_politics", cid))
        elif reason.startswith('title_only'):
            drop_outlet.append((f"{reason}:gate2_fp68", cid))
        else:
            keep_outlet.append(cid)

    print(f"tier 2 before: {len(rows):,}")
    print(f"  individuals kept (Politics)      {len(keep_individual):>6,}")
    print(f"  individuals dropped to tier 3    {len(drop_individual):>6,}")
    print(f"  title_only outlets to tier 3     {len(drop_outlet):>6,}")
    print(f"  topic-matched outlets kept       {len(keep_outlet):>6,}")
    print(f"tier 2 after:  {len(keep_individual) + len(keep_outlet):,}")

    if args.dry_run:
        con.close()
        return 0

    con.executemany("UPDATE channels SET tier_reason = ? WHERE channel_id = ?",
                    keep_individual)
    con.executemany(
        f"UPDATE channels SET tier = {TIER_DROP}, tier_reason = ? WHERE channel_id = ?",
        drop_individual + drop_outlet)
    con.commit()

    after = {r['tier']: r['n'] for r in con.execute(
        "SELECT tier, COUNT(*) AS n FROM channels GROUP BY tier")}
    print("\ntier      before    after")
    for tier in sorted(set(before) | set(after)):
        print(f"  {tier}     {before.get(tier, 0):>7,}  {after.get(tier, 0):>7,}")

    individuals = sum(1 for r in con.execute(
        "SELECT channel_id FROM channels WHERE tier = 2") if r[0] in persons)
    total2 = after.get(2, 0)
    print(f"\ntier 2 = {total2:,}: {individuals:,} individuals + "
          f"{total2 - individuals:,} stale topic-matched outlets")
    con.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
