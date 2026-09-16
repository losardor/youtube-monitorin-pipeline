#!/usr/bin/env python3
"""
2.3 — country provenance for individuals.

For a person, `snippet.country` on the channel is the better source: it says
where the channel operates. Wikidata `P27` is citizenship, which is a different
fact and frequently the wrong one for this purpose -- it is how Javier Milei,
an Argentine politician with Italian citizenship, lands under Italy.

So: take the channel's own country first, fall back to citizenship only when
the channel has none, and mark every row that used the fallback with
`reason='country_from_citizenship'` appended to tier_reason, so the error class
stays traceable in the data rather than living in a comment.

Citizenship is fetched from Wikidata (free, no YouTube quota) for the
individuals that need it.

Spends no YouTube quota.
"""

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.calibrate_rules import load_raw                        # noqa: E402
from scripts.fetch_occupations import ENDPOINT, USER_AGENT, QID_RE  # noqa: E402
from scripts.tier_frame import qids_of, load_candidates             # noqa: E402

CITIZENSHIP_QUERY = """
SELECT ?item ?countryLabel WHERE {
  VALUES ?item { %s }
  ?item wdt:P27 ?country .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
"""


def fetch_citizenship(qids, session, batch_size=200, delay=1.0) -> dict:
    out = {}
    for i in range(0, len(qids), batch_size):
        batch = qids[i:i + batch_size]
        values = ' '.join(f'wd:{q}' for q in batch)
        try:
            r = session.get(ENDPOINT,
                            params={'query': CITIZENSHIP_QUERY % values,
                                    'format': 'json'},
                            headers={'User-Agent': USER_AGENT},
                            timeout=180)
            r.raise_for_status()
        except Exception as e:
            print(f"  batch {i // batch_size + 1} failed: {type(e).__name__}")
            continue
        for b in r.json()['results']['bindings']:
            qid = b['item']['value'].rsplit('/', 1)[-1]
            out.setdefault(qid, b['countryLabel']['value'])
        time.sleep(delay)
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument('--db', default='data/youtube_monitoring.db')
    parser.add_argument('--raw-dir', default='data/raw/wikidata_confirm')
    parser.add_argument('--candidates', default='seeds/wikidata/frame_candidates.csv')
    parser.add_argument('--cache', default='data/wikidata_citizenship.json')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)

    raw_dir = Path(args.raw_dir)
    items, requested = load_raw(raw_dir, 'person_candidate')
    persons = set(requested)

    seeds = {}
    for row in load_candidates(args.candidates):
        seeds.setdefault(row['channel_id'], row)

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    rows = [r for r in con.execute(
        "SELECT channel_id, country, tier, tier_reason FROM channels "
        "WHERE tier IN (1, 2)") if r['channel_id'] in persons]

    from_channel, need_fallback = [], []
    for r in rows:
        cid = r['channel_id']
        api_country = (items.get(cid, {}).get('snippet', {}).get('country')
                       or r['country'])
        if api_country:
            from_channel.append((api_country, cid))
        else:
            need_fallback.append(cid)

    print(f"individuals at tier 1-2:            {len(rows):>6,}")
    print(f"  country from the channel:         {len(from_channel):>6,}")
    print(f"  no channel country, need P27:     {len(need_fallback):>6,}")

    # Citizenship only for the ones that actually need it.
    cache_path = Path(args.cache)
    citizenship = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    todo = sorted({q for cid in need_fallback for q in qids_of(seeds.get(cid, {}))
                   if q not in citizenship})
    if todo and not args.dry_run:
        print(f"  querying Wikidata for {len(todo):,} QIDs (free)")
        citizenship.update(fetch_citizenship(todo, requests.Session()))
        cache_path.write_text(json.dumps(citizenship, indent=0, sort_keys=True))

    fallback = []
    for cid in need_fallback:
        for qid in qids_of(seeds.get(cid, {})):
            if qid in citizenship:
                fallback.append((citizenship[qid], cid))
                break
    print(f"  resolved from citizenship:        {len(fallback):>6,}")
    print(f"  still unknown:                    "
          f"{len(need_fallback) - len(fallback):>6,}")

    if args.dry_run:
        con.close()
        return 0

    con.executemany("UPDATE channels SET country = ? WHERE channel_id = ?",
                    from_channel)
    # The flag rides on tier_reason so it survives in every export without a
    # further column, and so the Milei class of error is greppable.
    con.executemany("""
        UPDATE channels
           SET country = ?,
               tier_reason = CASE
                   WHEN tier_reason LIKE '%country_from_citizenship%'
                        THEN tier_reason
                   ELSE COALESCE(tier_reason, '') || ':country_from_citizenship'
               END
         WHERE channel_id = ?
    """, fallback)
    con.commit()

    flagged = con.execute(
        "SELECT COUNT(*) FROM channels "
        "WHERE tier_reason LIKE '%country_from_citizenship%'").fetchone()[0]
    print(f"\nrows flagged country_from_citizenship: {flagged:,}")
    con.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
