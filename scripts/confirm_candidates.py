#!/usr/bin/env python3
"""
YouTube-side confirmation pass for the Wikidata candidates (2.2 / 2.3).

SPENDS QUOTA: one channels.list call per 50 channels, 1 unit each.

Raw responses are archived under data/raw/wikidata_confirm/ so the calibration
can be recomputed, and the decision rule changed, without paying again.

Calibration: candidates already in tier 0 are labelled positives -- they are
known-good news channels that reached the frame independently, through
NewsGuard. Running them through the same checks gives a retention rate, which
is the closest thing available to a recall estimate for each rule.
"""

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.database import Database                                  # noqa: E402
from src.errors import QuotaExhausted                              # noqa: E402
from src.quota import QuotaGovernor, DAILY_FORBIDDEN_ENDPOINTS     # noqa: E402
from src.youtube_client import YouTubeAPIClient                    # noqa: E402

RAW_DIR = 'data/raw/wikidata_confirm'


def chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def fetch(client, ids: list, raw_dir: Path, label: str) -> dict:
    """channels.list over the id list, archiving every page."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    items = {}
    for n, batch in enumerate(chunks(ids, 50), start=1):
        page_path = raw_dir / f"{label}_{n:04d}.json"
        if page_path.exists():
            # Already paid for on an earlier run: reuse rather than re-spend.
            page = json.loads(page_path.read_text())
        else:
            try:
                page = client.channels_by_id(batch)
            except QuotaExhausted as e:
                print(f"  stopped at batch {n}: {e}")
                break
            page_path.write_text(json.dumps({
                '_requested': batch,
                '_fetched_at': datetime.now(timezone.utc).isoformat(),
                **page,
            }, indent=1))
        for item in page.get('items', []):
            items[item['id']] = item
        if n % 10 == 0:
            print(f"  {n} batches, {len(items):,} channels resolved")
    return items


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument('--db', default='data/youtube_monitoring.db')
    parser.add_argument('--ids', required=True,
                        help='JSON file: {"label": [channel_id, ...], ...}')
    parser.add_argument('--raw-dir', default=RAW_DIR)
    parser.add_argument('--budget', type=int, default=500)
    args = parser.parse_args(argv)

    groups = json.loads(Path(args.ids).read_text())
    total = sum(len(v) for v in groups.values())
    print(f"Groups: " + ', '.join(f"{k}={len(v):,}" for k, v in groups.items()))
    print(f"Total channels: {total:,}  ->  {math.ceil(total / 50):,} units\n")

    db = Database(db_path=args.db)
    governor = QuotaGovernor(db.conn, args.budget,
                             forbidden_endpoints=DAILY_FORBIDDEN_ENDPOINTS)
    import os
    key = os.environ.get('YOUTUBE_API_KEY')
    if not key:
        import yaml
        key = yaml.safe_load(open('config/config_comprehensive.yaml'))['api']['youtube_api_key']
    client = YouTubeAPIClient(api_key=key, governor=governor, allow_search=False)

    spent_before = governor.spent_today()
    raw_dir = Path(args.raw_dir)
    for label, ids in groups.items():
        print(f"{label}: {len(ids):,} ids")
        found = fetch(client, ids, raw_dir, label)
        print(f"  resolved {len(found):,} / {len(ids):,}")

    print(f"\nUnits spent this run: {governor.spent_today() - spent_before:,}")
    print(f"Ledger today: {governor.spend_by_endpoint()}")
    db.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
