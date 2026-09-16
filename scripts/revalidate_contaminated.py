#!/usr/bin/env python3
"""
Revalidate bug-contaminated entries in validation_progress.json.

Rationale
---------
YouTubeAPIClient.get_channel_info silently converts quota 403 responses into
None, which the main validator then records as "Channel not found" with
quota_cost=0. This script re-queries those entries on a day with spare quota,
preserving full audit history.

The script bypasses the buggy get_channel_info by calling _make_request
directly — that path correctly re-raises HttpError 403, so quota exhaustion
is explicit. As defense-in-depth we also abort on three consecutive
(quota_cost=0 AND success=False) responses.

Schema note
-----------
This codebase uses 'quota_cost' and 'error' on each entry (not 'cost' /
'reason' as in some earlier notes). The revalidation_history field uses
the same names to stay auditable.
"""

import argparse
import json
import logging
import os
import re
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
sys.path.insert(0, parent_dir)

import yaml
from googleapiclient.errors import HttpError

# _make_request now raises QuotaExhausted where it used to let a 403 HttpError
# through. Both are caught below so this script's abort path still fires.
from src.errors import QuotaExhausted
from src.youtube_client import YouTubeAPIClient

logger = logging.getLogger(__name__)

PROGRESS_FILE = os.path.join(parent_dir, 'data/validation/validation_progress.json')
CONFIG_FILE   = os.path.join(parent_dir, 'config/config_comprehensive.yaml')

URL_TYPES = ['channel_uc', 'handle', 'c_custom', 'user_legacy', 'other']
# Worst-case cost estimate per type for budget math.
COST_ESTIMATE = {'channel_uc': 1, 'handle': 1, 'c_custom': 100, 'user_legacy': 100, 'other': 100}


def classify_url(url: str) -> str:
    url = (url or '').strip()
    if '/channel/UC' in url: return 'channel_uc'
    if '/@' in url:          return 'handle'
    if '/c/' in url:         return 'c_custom'
    if '/user/' in url:      return 'user_legacy'
    return 'other'


def is_contaminated(entry: dict, pattern: re.Pattern) -> bool:
    """Default bug-signature: quota_cost=0 AND success=False AND error matches pattern."""
    if (entry.get('quota_cost') or 0) != 0: return False
    if entry.get('success') is not False:   return False
    return bool(pattern.search(entry.get('error') or ''))


def atomic_write_json(path: str, obj) -> None:
    """Write JSON atomically via tmp+fsync+rename."""
    d = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(prefix='validation_progress.', suffix='.tmp', dir=d)
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(obj, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try: os.unlink(tmp)
        except OSError: pass
        raise


def revalidate_one(client, url: str):
    """
    Call channels.list directly (bypassing get_channel_info's 403-swallow).

    Returns (channel_info_dict_or_None, quota_delta, quota_exceeded_bool).
    Raises on any non-quota HttpError so caller can decide what to do.
    """
    quota_before = client.quota_usage
    id_or_handle = client.extract_channel_id(url)
    if not id_or_handle:
        return None, 0, False

    try:
        # Handle form (@name) — use forHandle
        if id_or_handle.startswith('@'):
            request = client.youtube.channels().list(
                part='snippet,statistics,contentDetails,brandingSettings',
                forHandle=id_or_handle,
            )
            resp = client._make_request(
                lambda: request.execute(),
                quota_cost=1,
                api_method='channels.list_forHandle',
            )
            items = (resp or {}).get('items') or []
            return (items[0] if items else None), client.quota_usage - quota_before, False

        # Everything else — assume it's a channel ID and let the API decide.
        # Malformed/truncated IDs return items=[] (1 unit) or HTTP 400 (not quota).
        request = client.youtube.channels().list(
            part='snippet,statistics,contentDetails,brandingSettings',
            id=id_or_handle,
        )
        resp = client._make_request(
            lambda: request.execute(),
            quota_cost=1,
            api_method='channels.list',
        )
        items = (resp or {}).get('items') or []
        return (items[0] if items else None), client.quota_usage - quota_before, False

    except QuotaExhausted:
        # Real quota exhaustion — explicit, raised by _call.
        return None, client.quota_usage - quota_before, True
    except HttpError as e:
        if e.resp.status in (403, 429):
            return None, client.quota_usage - quota_before, True
        # 400/404/etc: treat as not found, not a crash.
        return None, client.quota_usage - quota_before, False


def build_updated_entry(original: dict, new_info: Optional[dict], new_cost: int, now_iso: str) -> dict:
    """Produce the new entry replacing the contaminated one. Preserves audit trail."""
    history = list(original.get('revalidation_history') or [])
    # Snapshot the original (minus revalidation_history itself) into history, tagged.
    snapshot = {k: v for k, v in original.items() if k != 'revalidation_history'}
    snapshot['superseded_by'] = f"revalidate_contaminated.py on {now_iso}"
    history.append(snapshot)

    if new_info is None:
        return {
            'url': original.get('url'),
            'domain': original.get('domain', ''),
            'brand_name': original.get('brand_name', ''),
            'success': False,
            'channel_id': None,
            'channel_title': None,
            'subscriber_count': None,
            'video_count': None,
            'error': 'Channel not found (deleted/private/suspended) [confirmed on revalidation]',
            'quota_cost': new_cost,
            'validated_at': now_iso,
            'revalidation_history': history,
        }

    stats = new_info.get('statistics') or {}
    snippet = new_info.get('snippet') or {}
    return {
        'url': original.get('url'),
        'domain': original.get('domain', ''),
        'brand_name': original.get('brand_name', ''),
        'success': True,
        'channel_id': new_info.get('id'),
        'channel_title': snippet.get('title'),
        'subscriber_count': stats.get('subscriberCount', 'Hidden'),
        'video_count': stats.get('videoCount', '0'),
        'error': None,
        'quota_cost': new_cost,
        'validated_at': now_iso,
        'revalidation_history': history,
    }


def main():
    parser = argparse.ArgumentParser(description='Revalidate bug-contaminated entries in validation_progress.json')
    parser.add_argument('--dry-run', action='store_true', help='List what would be re-validated; no API calls; no mutations.')
    parser.add_argument('--date-filter', action='append', default=[],
                        help='YYYY-MM-DD — only entries with validated_at on this date. Repeatable (any-of). Omit for all dates.')
    parser.add_argument('--url-types', default='channel_uc,handle',
                        help=f"Comma-separated URL types to include. Options: {','.join(URL_TYPES)}. Default: channel_uc,handle (cheap).")
    parser.add_argument('--max-quota', type=int, default=2500,
                        help='Hard cap on estimated quota cost. Default 2500.')
    parser.add_argument('--contamination-filter', default=r'not found',
                        help="Regex against entry.error (case-insensitive). Default 'not found'.")
    parser.add_argument('--delay', type=float, default=0.3,
                        help='Sleep between API calls (sec). Default 0.3.')
    parser.add_argument('--checkpoint-every', type=int, default=25,
                        help='Atomic write progress file every N live-run updates. Default 25.')
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format='%(asctime)s  %(levelname)s  %(message)s')

    url_types = [t.strip() for t in args.url_types.split(',') if t.strip()]
    unknown = [t for t in url_types if t not in URL_TYPES]
    if unknown:
        print(f"ERROR: unknown url-types: {unknown}. Allowed: {URL_TYPES}", file=sys.stderr)
        return 2
    try:
        pattern = re.compile(args.contamination_filter, re.IGNORECASE)
    except re.error as e:
        print(f"ERROR: bad regex: {e}", file=sys.stderr)
        return 2

    # Load progress
    with open(PROGRESS_FILE) as f:
        progress = json.load(f)
    results = progress.get('results') or []
    print(f"Progress file loaded: {len(results)} entries")

    # Select entries
    date_set = set(args.date_filter)
    selected_idx = []
    for i, entry in enumerate(results):
        if not is_contaminated(entry, pattern):
            continue
        if date_set:
            day = (entry.get('validated_at') or '')[:10]
            if day not in date_set:
                continue
        if classify_url(entry.get('url', '')) not in url_types:
            continue
        selected_idx.append(i)

    # Breakdown
    from collections import Counter
    bucket_counts = Counter(classify_url(results[i].get('url','')) for i in selected_idx)
    date_counts = Counter((results[i].get('validated_at') or '')[:10] for i in selected_idx)
    est_cost = sum(COST_ESTIMATE[classify_url(results[i].get('url',''))] for i in selected_idx)

    print()
    print("=" * 70)
    print(f"Mode: {'DRY-RUN' if args.dry_run else 'LIVE'}")
    print(f"Date filter: {sorted(date_set) if date_set else '(all)'}")
    print(f"URL types: {url_types}")
    print(f"Contamination regex: {pattern.pattern}")
    print(f"Max quota cap: {args.max_quota}")
    print("-" * 70)
    print(f"Selected entries: {len(selected_idx)}")
    print(f"By URL type:")
    for k in URL_TYPES:
        if bucket_counts.get(k):
            print(f"  {k:12}: {bucket_counts[k]}")
    print(f"By date:")
    for d in sorted(date_counts):
        print(f"  {d}: {date_counts[d]}")
    print(f"Estimated worst-case cost: {est_cost} units")
    print("=" * 70)
    print()

    if est_cost > args.max_quota:
        print(f"ABORT: estimated cost {est_cost} exceeds --max-quota {args.max_quota}")
        return 3

    if args.dry_run:
        print("DRY-RUN — no API calls, no mutations. Rerun without --dry-run to execute.")
        return 0

    if not selected_idx:
        print("Nothing to do.")
        return 0

    # Backup
    ts = datetime.now().strftime('%Y%m%dT%H%M%S')
    backup_path = f"{PROGRESS_FILE}.bak_before_revalidation_{ts}"
    import shutil
    shutil.copy2(PROGRESS_FILE, backup_path)
    print(f"Backup: {backup_path}")

    # API client
    with open(CONFIG_FILE) as f:
        config = yaml.safe_load(f)
    client = YouTubeAPIClient(
        api_key=config['api']['youtube_api_key'],
        max_retries=config['api'].get('max_retries', 3),
        retry_delay=config['api'].get('retry_delay', 2),
    )

    stats = {'attempted': 0, 'recovered': 0, 'still_failed': 0, 'quota_used': 0}
    consecutive_zero_cost_fail = 0
    quota_aborted = False
    bug_signature_aborted = False
    updated_since_checkpoint = 0
    t0 = time.time()

    try:
        for n, idx in enumerate(selected_idx, 1):
            entry = results[idx]
            url = entry.get('url', '')
            btype = classify_url(url)

            stats['attempted'] += 1
            info, cost, quota_exceeded = revalidate_one(client, url)
            stats['quota_used'] += cost
            now_iso = datetime.now().isoformat()

            if quota_exceeded:
                print(f"[{n}/{len(selected_idx)}] {url[:70]}  -> QUOTA 403 propagated. Aborting.")
                quota_aborted = True
                break

            new_entry = build_updated_entry(entry, info, cost, now_iso)
            old_status = 'fail(cost=0)'
            if info is not None:
                stats['recovered'] += 1
                new_status = f"OK channel_id={new_entry['channel_id']} cost={cost}"
            else:
                stats['still_failed'] += 1
                new_status = f"FAIL(confirmed) cost={cost}"

            # Bug-signature: 3 consecutive cost=0 failures suggest the swallow bug is alive.
            if info is None and cost == 0:
                consecutive_zero_cost_fail += 1
            else:
                consecutive_zero_cost_fail = 0
            if consecutive_zero_cost_fail >= 3:
                print(f"[{n}/{len(selected_idx)}] BUG SIGNATURE: 3 consecutive cost=0 + fail. Aborting before further damage.")
                bug_signature_aborted = True
                # Still apply THIS entry so progress isn't lost, but don't continue.
                results[idx] = new_entry
                updated_since_checkpoint += 1
                break

            results[idx] = new_entry
            updated_since_checkpoint += 1

            brand = (entry.get('brand_name') or entry.get('domain') or '')[:30]
            print(f"[{n:>4}/{len(selected_idx)}] {brand:<30} {url[:55]:<55} {old_status} -> {new_status}")

            # Periodic checkpoint
            if updated_since_checkpoint >= args.checkpoint_every:
                progress['results'] = results
                atomic_write_json(PROGRESS_FILE, progress)
                updated_since_checkpoint = 0

            time.sleep(args.delay)

    except KeyboardInterrupt:
        print("\nInterrupted by user. Saving partial progress before exit.")
    except QuotaExhausted as e:
        print(f"\nQuota exhausted outside revalidate_one handler: {e}. Saving partial progress.")
        quota_aborted = True
    except HttpError as e:
        if e.resp.status in (403, 429):
            print(f"\nAPI returned {e.resp.status} outside revalidate_one handler. Quota likely exhausted. Saving partial progress.")
            quota_aborted = True
        else:
            print(f"\nAPI error (non-quota): {e}. Saving partial progress and re-raising.")
            # Final save first so partial progress is durable.
            progress['results'] = results
            atomic_write_json(PROGRESS_FILE, progress)
            raise

    # Final durable write
    progress['results'] = results
    atomic_write_json(PROGRESS_FILE, progress)

    elapsed = time.time() - t0
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Attempted:      {stats['attempted']} / {len(selected_idx)}")
    print(f"Recovered:      {stats['recovered']} (newly successful)")
    print(f"Still failed:   {stats['still_failed']} (genuinely not found)")
    print(f"Quota used:     {stats['quota_used']} (est was {est_cost})")
    print(f"Elapsed:        {elapsed:.1f}s")
    print(f"Backup:         {backup_path}")
    if quota_aborted:
        print("Exit:           ABORTED on quota 403")
        return 4
    if bug_signature_aborted:
        print("Exit:           ABORTED on bug-signature (3 consecutive cost=0 fails)")
        return 5
    print("Exit:           OK")
    return 0


if __name__ == '__main__':
    sys.exit(main())
