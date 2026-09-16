#!/usr/bin/env python3
"""
Fetch the full P106 occupation list for the commentator stratum's Wikidata items.

Costs no YouTube quota: this queries the Wikidata Query Service, which is a
separate, free service. It exists because `wd_class` in frame_candidates.csv
holds only the class that put the item in the frame -- for 3,112 of the 4,672
commentator rows that is the single label `journalist`, which says nothing
about the other occupations the person also has. Deciding whether someone is a
journalist who once sang, or a singer who once wrote a column, needs the whole
P106 list.

Output: {QID: [occupation labels]} as JSON.

Batched with VALUES, which keeps the query count low and is gentler on the
public endpoint than one query per item.
"""

import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent

ENDPOINT = 'https://query.wikidata.org/sparql'

# A descriptive User-Agent is required by the WDQS usage policy.
USER_AGENT = ('youtube-monitoring-pipeline/1.0 '
              '(computational social science research; '
              'https://github.com/losardor/youtube-monitorin-pipeline)')

QUERY = """
SELECT ?item ?occupationLabel WHERE {
  VALUES ?item { %s }
  ?item wdt:P106 ?occupation .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
"""


QID_RE = re.compile(r'Q[1-9][0-9]*')


def load_qids(candidates: str, stratum: str) -> list:
    """
    Distinct, well-formed QIDs for one stratum.

    13 rows in the pool carry a pipe-joined pair ("Q20963418|Q4160936"): one
    channel mapped to two Wikidata items. Splitting on the pipe is required --
    passing the raw value through makes `wd:Q123|Q456`, which is invalid SPARQL
    and fails the whole batch with a 400, taking 250 good QIDs with it.
    """
    csv.field_size_limit(sys.maxsize)
    with open(candidates) as f:
        rows = [r for r in csv.DictReader(f) if r['stratum'] == stratum]
    seen, out = set(), []
    for r in rows:
        for qid in QID_RE.findall(r.get('wd_item') or ''):
            if qid not in seen:
                seen.add(qid)
                out.append(qid)
    return out


def run_batch(qids: list, session: requests.Session, timeout: int = 180) -> dict:
    values = ' '.join(f'wd:{q}' for q in qids)
    response = session.get(
        ENDPOINT,
        params={'query': QUERY % values, 'format': 'json'},
        headers={'User-Agent': USER_AGENT, 'Accept': 'application/sparql-results+json'},
        timeout=timeout,
    )
    response.raise_for_status()
    out = {}
    for binding in response.json()['results']['bindings']:
        qid = binding['item']['value'].rsplit('/', 1)[-1]
        label = binding['occupationLabel']['value']
        out.setdefault(qid, []).append(label)
    return out


def bisect_batch(batch: list, session: requests.Session, delay: float) -> tuple:
    """
    Split a failing batch until the offending ids are isolated.

    A single malformed or rejected id would otherwise cost every other id in
    its batch, which is how 2,250 good QIDs went missing on the first run.
    """
    if len(batch) == 1:
        try:
            return run_batch(batch, session), []
        except Exception:
            return {}, batch

    mid = len(batch) // 2
    found, bad = {}, []
    for half in (batch[:mid], batch[mid:]):
        try:
            found.update(run_batch(half, session))
        except Exception:
            sub_found, sub_bad = bisect_batch(half, session, delay)
            found.update(sub_found)
            bad.extend(sub_bad)
        time.sleep(delay)
    return found, bad


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument('--candidates', default='seeds/wikidata/frame_candidates.csv')
    parser.add_argument('--stratum', default='commentator')
    parser.add_argument('--out', default='data/wikidata_occupations.json')
    parser.add_argument('--batch-size', type=int, default=250)
    parser.add_argument('--delay', type=float, default=1.0,
                        help='Seconds between queries; be polite to WDQS')
    parser.add_argument('--limit', type=int, default=None,
                        help='Only query the first N QIDs (for a smoke test)')
    args = parser.parse_args(argv)

    qids = load_qids(args.candidates, args.stratum)
    if args.limit:
        qids = qids[:args.limit]
    print(f"QIDs to query: {len(qids):,} "
          f"in {(len(qids) + args.batch_size - 1) // args.batch_size} batches")

    # Resume support: an interrupted run keeps what it already fetched.
    out_path = Path(args.out)
    result = {}
    if out_path.exists():
        result = json.loads(out_path.read_text())
        print(f"Resuming: {len(result):,} QIDs already fetched")

    todo = [q for q in qids if q not in result]
    print(f"Remaining: {len(todo):,}")

    session = requests.Session()
    failures = []

    for i in range(0, len(todo), args.batch_size):
        batch = todo[i:i + args.batch_size]
        n = i // args.batch_size + 1
        try:
            found = run_batch(batch, session)
        except Exception as e:
            print(f"  batch {n}: failed ({type(e).__name__}: {str(e)[:80]}), bisecting")
            found, bad = bisect_batch(batch, session, args.delay)
            if bad:
                print(f"    {len(bad)} QID(s) rejected individually: {bad[:5]}")
                failures.extend(bad)

        # Items with no P106 return no rows; record them as empty so the
        # resume logic does not re-query them forever.
        for qid in batch:
            result[qid] = found.get(qid, [])

        print(f"  batch {n}: {len(batch)} queried, "
              f"{sum(1 for q in batch if result[q])} with occupations")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, indent=0, sort_keys=True))
        time.sleep(args.delay)

    with_occ = sum(1 for v in result.values() if v)
    print(f"\nWrote {out_path}: {len(result):,} QIDs, "
          f"{with_occ:,} with at least one occupation")
    if failures:
        print(f"WARNING: {len(failures):,} QIDs failed; re-run to retry them")
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
