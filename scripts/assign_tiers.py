#!/usr/bin/env python3
"""
Recency check and tier assignment for the Wikidata candidates (2.2 / 2.3).

Admission rule, fixed after calibration against the 240 labelled positives:

    topic OR (title AND NOT gaming/music-tagged)

where a topic match is Society, Politics or Business. `News` is NOT part of
the check: it does not occur once in 3,423 channels, so including it only
implied a precision it never delivered. Sport is deliberately NOT a
disqualifying topic -- genuine local newspapers are routinely Sport-tagged,
and excluding them would drop exactly the frame-gap the study is looking for.

The admitting check is recorded in channels.tier_reason as 'topic',
'title_only' or 'topic+title', which is what makes Gate 2 cheap to act on: a
stratum that fails the hand check is demoted with an UPDATE, no quota.

Tier assignment after the recency check (newest upload within 180 days):

  outlets      pass -> tier 1
               fail -> tier 2, reason suffixed ':stale'
               unresolved / zero videos -> tier 3
  individuals  pass -> tier 2
               fail -> tier 3

Individuals never go above tier 2: the brief does not put them there.

SPENDS QUOTA: 1 unit per admitted channel (one playlistItems page).
Responses are archived so this can be recomputed for free.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.calibrate_rules import load_raw, evaluate, non_news       # noqa: E402
from src.database import Database                                      # noqa: E402
from src.errors import QuotaExhausted, ItemUnavailable, APIError       # noqa: E402
from src.quota import QuotaGovernor, DAILY_FORBIDDEN_ENDPOINTS         # noqa: E402
from src.youtube_client import YouTubeAPIClient                        # noqa: E402

RECENCY_DAYS = 180

TIER_OUTLET_PASS = 1
TIER_OUTLET_STALE = 2
TIER_PERSON_PASS = 2
TIER_REJECT = 3


def admits(record) -> str:
    """
    The admitting check, or None if the record is not admitted.

    Returns 'topic', 'topic+title' or 'title_only'.
    """
    if not record['resolved'] or not record['has_videos']:
        return None
    if record['topic']:
        return 'topic+title' if record['title'] else 'topic'
    if record['title'] and not non_news(record):
        return 'title_only'
    return None


def newest_upload(client, playlist_id: str, raw_dir: Path, cid: str):
    """
    Date of the newest upload, via one playlistItems page (1 unit).

    Archived per channel so a re-run costs nothing.
    """
    cache = raw_dir / f"{cid}.json"
    if cache.exists():
        page = json.loads(cache.read_text())
    else:
        page = client.playlist_items(playlist_id)
        cache.write_text(json.dumps(page))

    newest = None
    for item in page.get('items', []):
        published = item.get('contentDetails', {}).get('videoPublishedAt')
        if published and (newest is None or published > newest):
            newest = published
    return newest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument('--db', default='data/youtube_monitoring.db')
    parser.add_argument('--raw-dir', default='data/raw/wikidata_confirm')
    parser.add_argument('--recency-dir', default='data/raw/wikidata_recency')
    parser.add_argument('--budget', type=int, default=9000)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)

    raw_dir = Path(args.raw_dir)
    meta = json.loads((raw_dir / 'confirm_meta.json').read_text())
    recency_dir = Path(args.recency_dir)
    recency_dir.mkdir(parents=True, exist_ok=True)

    # Outlets first, as instructed: they are the primary expansion.
    groups = {}
    for label in ('outlet_candidate', 'person_candidate'):
        items, requested = load_raw(raw_dir, label)
        records = evaluate(items, requested, meta)
        for r in records:
            r['_uploads'] = ((items.get(r['channel_id']) or {})
                             .get('contentDetails', {})
                             .get('relatedPlaylists', {})
                             .get('uploads'))
        groups[label] = records

    admitted = {g: [(r, admits(r)) for r in recs if admits(r)]
                for g, recs in groups.items()}
    for g, adm in admitted.items():
        print(f"{g:<18} admitted {len(adm):>6,} of {len(groups[g]):>6,}")
    total = sum(len(a) for a in admitted.values())
    print(f"playlistItems calls needed: {total:,}\n")

    if args.dry_run:
        return 0

    db = Database(db_path=args.db)
    governor = QuotaGovernor(db.conn, args.budget,
                             forbidden_endpoints=DAILY_FORBIDDEN_ENDPOINTS)
    key = os.environ.get('YOUTUBE_API_KEY')
    if not key:
        import yaml
        key = yaml.safe_load(open('config/config_comprehensive.yaml'))['api']['youtube_api_key']
    client = YouTubeAPIClient(api_key=key, governor=governor, allow_search=False)

    spent_before = governor.spent_today()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=RECENCY_DAYS)).isoformat()
    updates, stats = [], {}

    for group, is_outlet in (('outlet_candidate', True), ('person_candidate', False)):
        fresh = stale = broken = 0
        for n, (record, reason) in enumerate(admitted[group], start=1):
            cid = record['channel_id']
            playlist = record['_uploads']
            newest = None
            if playlist:
                try:
                    newest = newest_upload(client, playlist, recency_dir, cid)
                except QuotaExhausted as e:
                    print(f"  {group}: stopped at {n:,}: {e}")
                    break
                except (ItemUnavailable, APIError):
                    newest = None

            if newest and newest >= cutoff:
                tier = TIER_OUTLET_PASS if is_outlet else TIER_PERSON_PASS
                updates.append((tier, reason, cid))
                fresh += 1
            else:
                if is_outlet:
                    updates.append((TIER_OUTLET_STALE, f"{reason}:stale", cid))
                else:
                    updates.append((TIER_REJECT, f"{reason}:stale", cid))
                stale += 1
            if playlist is None:
                broken += 1
            if n % 250 == 0:
                print(f"  {group}: {n:,}/{len(admitted[group]):,}  "
                      f"fresh {fresh:,} stale {stale:,}  "
                      f"units {governor.spent_today() - spent_before:,}")

        # Not admitted: recorded, never collected.
        rejected = [r for r in groups[group] if not admits(r)]
        for r in rejected:
            why = ('unresolved' if not r['resolved']
                   else 'zero_videos' if not r['has_videos']
                   else 'no_topic_or_title')
            updates.append((TIER_REJECT, why, r['channel_id']))

        stats[group] = {'fresh': fresh, 'stale': stale,
                        'no_playlist': broken, 'rejected': len(rejected)}
        print(f"  {group}: fresh {fresh:,}, stale {stale:,}, "
              f"rejected {len(rejected):,}")

    # Only write rows that are not already in the validated frame: tier 0 is
    # never overwritten by this pass.
    tier0 = {r[0] for r in db.conn.execute("SELECT channel_id FROM channels WHERE tier = 0")}
    writable = [(t, why, cid) for t, why, cid in updates if cid not in tier0]
    print(f"\nrows to write: {len(writable):,} "
          f"({len(updates) - len(writable):,} skipped, already tier 0)")

    seed_meta = meta
    db.conn.executemany("""
        INSERT INTO channels (channel_id, channel_url, tier, tier_reason,
                              wd_item, wd_class, status, last_checked)
        VALUES (?, ?, ?, ?, ?, ?, NULL, NULL)
        ON CONFLICT(channel_id) DO UPDATE SET
            tier = excluded.tier,
            tier_reason = excluded.tier_reason,
            wd_item = COALESCE(channels.wd_item, excluded.wd_item),
            wd_class = COALESCE(channels.wd_class, excluded.wd_class)
    """, [(cid, f"https://www.youtube.com/channel/{cid}", t, why,
           seed_meta.get(cid, {}).get('wd_item'),
           seed_meta.get(cid, {}).get('wd_class')) for t, why, cid in writable])
    db.conn.commit()

    spent = governor.spent_today() - spent_before
    print(f"\nUnits spent this run: {spent:,}")
    print("Tier distribution:")
    for row in db.conn.execute(
            "SELECT tier, COUNT(*) FROM channels GROUP BY tier ORDER BY tier"):
        print(f"  tier {row[0]}: {row[1]:,}")
    print("tier_reason distribution (tier 1 and 2):")
    for row in db.conn.execute(
            "SELECT tier, tier_reason, COUNT(*) FROM channels "
            "WHERE tier IN (1,2) GROUP BY tier, tier_reason ORDER BY tier, 3 DESC"):
        print(f"  tier {row[0]}  {row[1] or '(none)':<24} {row[2]:,}")
    db.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
