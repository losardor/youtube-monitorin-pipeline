#!/usr/bin/env python3
"""
2.5 — audit where the NewsGuard frame and the Wikidata frame disagree.

Two lists, answering two different questions:

**A. NewsGuard outlets with a Wikidata channel we failed to resolve.**
Outlets whose validation failed, but whose domain or brand name matches a
Wikidata item that does carry a YouTube channel. These are re-validation
candidates, and a cheap one: we already hold the channel id, so confirming one
costs 1 unit via channels.list rather than the 100 a `/c/` or `/user/` URL
would cost through search.list. 286 such URLs are still deferred pending the
1M quota increase; any that appear here can be recovered for 1 unit instead.

**B. Wikidata tier-1 outlets absent from NewsGuard.**
Active, topic-confirmed news outlets that the NewsGuard frame never contained.
These are the frame gap, and belong in the paper's limitations section: the
sampling frame is NewsGuard's coverage, which is uneven by country and skews
to outlets large enough to have been rated.

Both lists are candidates for human review, not verified mappings. Name
matching cannot fully separate distinct outlets that share a name: "La Tribune"
and "The Tribune" reduce to the same token once articles are dropped, and
news.com.au and News.Ro share a domain root. `match_method` is recorded on
every row so a reviewer can weight them -- `domain` and `brand_exact` are
strong, `brand_subset` is the one to check.

Spends no quota. Output: two CSVs plus a printed summary.
"""

import argparse
import csv
import json
import re
import sqlite3
import sys
import unicodedata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.tier_frame import load_candidates, tokens  # noqa: E402


def domain_root(value: str) -> str:
    """Bare second-level domain, for matching a seed label to a NewsGuard row."""
    if not value:
        return ''
    value = re.sub(r'^https?://', '', value.strip().lower())
    value = value.split('/')[0]
    value = re.sub(r'^www\.', '', value)
    parts = value.split('.')
    return parts[0] if parts else ''


def fold(text: str) -> str:
    decomposed = unicodedata.normalize('NFKD', text or '')
    return ''.join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument('--db', default='data/youtube_monitoring.db')
    parser.add_argument('--candidates', default='seeds/wikidata/frame_candidates.csv')
    parser.add_argument('--validation', default='data/validation/validation_progress.json')
    parser.add_argument('--out-dir', default='reports')
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    candidates = load_candidates(args.candidates)
    validation = json.loads(Path(args.validation).read_text())['results']

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    in_db = {r['channel_id']: r for r in con.execute(
        "SELECT channel_id, tier, tier_reason, source_domain FROM channels")}

    # ---- list A: unresolved NewsGuard outlets that Wikidata can rescue -----
    failures = [r for r in validation if r.get('success') not in (True, 'True')]

    # Index Wikidata outlets by domain root and by folded label tokens.
    by_root, by_token = {}, {}
    for row in candidates:
        if row['stratum'] != 'outlet':
            continue
        label = row.get('label') or ''
        root = domain_root(label)
        if root:
            by_root.setdefault(root, row)
        for token in tokens(label):
            by_token.setdefault(token, []).append(row)

    rescues, seen = [], set()
    for entry in failures:
        domain = (entry.get('domain') or '').strip()
        brand = (entry.get('brand_name') or '').strip()
        root = domain_root(domain)

        # Domain root is the reliable key: a NewsGuard row and a Wikidata
        # item naming the same site agree on it.
        match = by_root.get(root) if root else None
        method = 'domain' if match else None

        if match is None and brand:
            # Brand matching must be strict, and containment alone is not
            # strict enough: a one-token label swallows anything containing it
            # ("Press TV Francais" -> "The News-Press", "Radio Gong 96.3" ->
            # "3 News"). Accept equal token sets, or containment only when the
            # contained side carries at least two tokens.
            brand_tokens = tokens(brand)
            if brand_tokens:
                for token in brand_tokens:
                    for cand in by_token.get(token, []):
                        cand_tokens = tokens(cand.get('label', ''))
                        if not cand_tokens:
                            continue
                        if brand_tokens == cand_tokens:
                            match, method = cand, 'brand_exact'
                            break
                        contained = (brand_tokens if brand_tokens <= cand_tokens
                                     else cand_tokens if cand_tokens <= brand_tokens
                                     else None)
                        if contained is not None and len(contained) >= 2:
                            match, method = cand, 'brand_subset'
                            break
                    if match:
                        break
        if match is None:
            continue

        cid = match['channel_id']
        key = (entry.get('url'), cid)
        if key in seen:
            continue
        seen.add(key)
        rescues.append({
            'newsguard_domain': domain,
            'newsguard_brand': brand,
            'failed_url': entry.get('url'),
            'failure_reason': entry.get('error'),
            'wikidata_channel_id': cid,
            'wikidata_label': match.get('label'),
            'wd_item': match.get('wd_item'),
            'match_method': method,
            'already_in_db': 'yes' if cid in in_db else 'no',
            'tier_if_known': in_db[cid]['tier'] if cid in in_db else '',
            'collected': ('yes' if cid in in_db and in_db[cid]['tier'] <= 2
                          else 'no'),
            'recovery_cost_units': 1,
        })

    path_a = out_dir / 'coverage_newsguard_unresolved.csv'
    with open(path_a, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rescues[0].keys()) if rescues else
                           ['newsguard_domain'])
        w.writeheader()
        w.writerows(rescues)

    # ---- list B: Wikidata tier-1 outlets absent from NewsGuard ------------
    newsguard_domains = {domain_root(r.get('domain') or '')
                         for r in validation if r.get('domain')}
    newsguard_domains.discard('')

    seed_by_channel = {}
    for row in candidates:
        seed_by_channel.setdefault(row['channel_id'], row)

    gaps = []
    for cid, row in in_db.items():
        if row['tier'] != 1:
            continue
        seed = seed_by_channel.get(cid)
        if seed is None:
            continue
        label_root = domain_root(seed.get('label') or '')
        if label_root and label_root in newsguard_domains:
            continue        # NewsGuard knows this outlet
        if row['source_domain']:
            continue        # it came in through NewsGuard anyway
        gaps.append({
            'channel_id': cid,
            'label': seed.get('label'),
            'wd_item': seed.get('wd_item'),
            'wd_class': seed.get('wd_class'),
            'country': seed.get('country'),
            'language': seed.get('language'),
            'tier_reason': row['tier_reason'],
        })

    path_b = out_dir / 'coverage_wikidata_frame_gap.csv'
    with open(path_b, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(gaps[0].keys()) if gaps else ['channel_id'])
        w.writeheader()
        w.writerows(gaps)

    print("A. NewsGuard outlets with a Wikidata channel we failed to resolve")
    print(f"   validation failures examined:     {len(failures):>6,}")
    print(f"   with a matching Wikidata channel: {len(rescues):>6,}")
    print(f"   already in the database:          "
          f"{sum(1 for r in rescues if r['already_in_db'] == 'yes'):>6,}")
    print(f"   recoverable at 1 unit each:       "
          f"{sum(1 for r in rescues if r['already_in_db'] == 'no'):>6,}")
    from collections import Counter as _C
    print("   by match method: " + ", ".join(
        f"{k} {v}" for k, v in _C(r['match_method'] for r in rescues).items()))
    held_uncollected = [r for r in rescues if r['already_in_db'] == 'yes'
                        and r['collected'] == 'no']
    print(f"   held but NOT collected (tier 3):  {len(held_uncollected):>6,}"
          "   <- promotion candidates")
    print(f"   -> {path_a}")
    print("   NB: candidates for review, not verified mappings -- shared names"
          " (La Tribune / The Tribune) survive this matching.")

    print("\nB. Wikidata tier-1 outlets absent from NewsGuard (frame gap)")
    print(f"   tier-1 outlets:                   "
          f"{sum(1 for r in in_db.values() if r['tier'] == 1):>6,}")
    print(f"   absent from NewsGuard:            {len(gaps):>6,}")
    from collections import Counter
    for country, n in Counter(g['country'] or '(none)' for g in gaps).most_common(8):
        print(f"     {country:<28} {n:>5,}")
    print(f"   -> {path_b}")

    con.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
