#!/usr/bin/env python3
"""
Validate all YouTube channel URLs before production collection.
Tests that each unique URL can be resolved and returns channel metadata.
"""

import sys
import os
import time
import json
from datetime import datetime
from pathlib import Path

# Add parent directory to path
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
sys.path.insert(0, parent_dir)

import pandas as pd
import yaml
from src.youtube_client import YouTubeAPIClient
from src.utils.helpers import extract_channel_id_from_url


def load_config():
    """Load configuration"""
    config_path = os.path.join(parent_dir, 'config/config_comprehensive.yaml')
    with open(config_path) as f:
        return yaml.safe_load(f)


def get_unique_urls(sources_path):
    """Get unique YouTube URLs with metadata"""
    df = pd.read_csv(sources_path, encoding='utf-8')

    # Get rows with YouTube URLs
    df_with_youtube = df[df['Youtube'].notna() & (df['Youtube'].str.strip() != '')]

    # Group by unique URL, keep first occurrence's metadata
    unique_urls = {}
    for _, row in df_with_youtube.iterrows():
        url = str(row['Youtube']).strip()
        if url not in unique_urls:
            domain = row.get('Domain', '')
            brand = row.get('Brand Name', '')
            # Handle NaN values
            domain = str(domain) if pd.notna(domain) else ''
            brand = str(brand) if pd.notna(brand) else ''
            unique_urls[url] = {
                'url': url,
                'domain': domain,
                'brand_name': brand,
            }

    return list(unique_urls.values())


def load_progress(progress_file):
    """Load progress from previous run"""
    if os.path.exists(progress_file):
        with open(progress_file) as f:
            return json.load(f)
    return {'validated': [], 'results': []}


def save_progress(progress_file, progress):
    """Save progress for resume"""
    with open(progress_file, 'w') as f:
        json.dump(progress, f, indent=2)


def validate_channel(client, url):
    """
    Validate a single channel URL.
    Returns: (success, channel_id, channel_title, subscriber_count, video_count, error_message)
    """
    try:
        # Extract identifier from URL
        channel_id = extract_channel_id_from_url(url)
        if not channel_id:
            return False, None, None, None, None, "Could not extract channel ID from URL"

        # Try to get channel info
        channel_info = client.get_channel_info(channel_id)

        if not channel_info:
            return False, channel_id, None, None, None, "Channel not found (deleted/private/suspended)"

        # Extract metadata
        title = channel_info.get('snippet', {}).get('title', 'Unknown')
        stats = channel_info.get('statistics', {})
        subscriber_count = stats.get('subscriberCount', 'Hidden')
        video_count = stats.get('videoCount', '0')
        actual_channel_id = channel_info.get('id', channel_id)

        return True, actual_channel_id, title, subscriber_count, video_count, None

    except Exception as e:
        error_msg = str(e)
        if 'quota' in error_msg.lower():
            raise  # Re-raise quota errors to stop validation
        return False, None, None, None, None, error_msg


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Validate YouTube channel URLs')
    parser.add_argument('--sources', default='data/sources.csv', help='Path to sources CSV')
    parser.add_argument('--resume', action='store_true', help='Resume from previous run')
    parser.add_argument('--limit', type=int, help='Limit number of URLs to validate')
    parser.add_argument('--delay', type=float, default=0.5, help='Delay between API calls (seconds)')
    args = parser.parse_args()

    print("=" * 70)
    print("YOUTUBE CHANNEL URL VALIDATION")
    print("=" * 70)
    print()

    # Setup paths
    sources_path = os.path.join(parent_dir, args.sources)
    output_dir = os.path.join(parent_dir, 'data/validation')
    os.makedirs(output_dir, exist_ok=True)

    progress_file = os.path.join(output_dir, 'validation_progress.json')
    results_file = os.path.join(output_dir, 'validation_results.csv')

    # Load config and initialize client
    config = load_config()
    client = YouTubeAPIClient(
        api_key=config['api']['youtube_api_key'],
        max_retries=config['api']['max_retries'],
        retry_delay=config['api']['retry_delay']
    )

    # Get unique URLs
    print(f"Loading sources from {sources_path}...")
    urls = get_unique_urls(sources_path)
    print(f"Found {len(urls)} unique YouTube URLs to validate")
    print()

    # Load progress if resuming
    progress = {'validated': [], 'results': []}
    if args.resume:
        progress = load_progress(progress_file)
        print(f"Resuming from previous run: {len(progress['validated'])} already validated")

    # Filter out already validated URLs
    validated_set = set(progress['validated'])
    urls_to_validate = [u for u in urls if u['url'] not in validated_set]

    if args.limit:
        urls_to_validate = urls_to_validate[:args.limit]

    print(f"URLs to validate in this run: {len(urls_to_validate)}")
    print(f"Estimated quota cost: {len(urls_to_validate)} - {len(urls_to_validate) * 100} units")
    print("  (1 unit per direct lookup, up to 100 if search fallback needed)")
    print()

    if not urls_to_validate:
        print("All URLs already validated!")
        return

    # Validate URLs
    stats = {
        'success': 0,
        'failed': 0,
        'quota_used': 0
    }

    try:
        for idx, url_info in enumerate(urls_to_validate, 1):
            url = url_info['url']
            brand = url_info.get('brand_name') or url_info.get('domain') or 'Unknown'
            # Ensure brand is a string
            brand = str(brand) if brand else 'Unknown'

            print(f"[{idx}/{len(urls_to_validate)}] {brand[:40]:<40} ", end='', flush=True)

            quota_before = client.quota_usage
            success, channel_id, title, subs, videos, error = validate_channel(client, url)
            quota_after = client.quota_usage

            quota_cost = quota_after - quota_before
            stats['quota_used'] += quota_cost

            result = {
                'url': url,
                'domain': url_info['domain'],
                'brand_name': url_info['brand_name'],
                'success': success,
                'channel_id': channel_id,
                'channel_title': title,
                'subscriber_count': subs,
                'video_count': videos,
                'error': error,
                'quota_cost': quota_cost,
                'validated_at': datetime.now().isoformat()
            }

            progress['results'].append(result)
            progress['validated'].append(url)

            if success:
                stats['success'] += 1
                print(f"✓ {title[:30] if title else 'OK'} ({videos} videos)")
            else:
                stats['failed'] += 1
                print(f"✗ {error[:40] if error else 'Unknown error'}")

            # Save progress every 50 URLs
            if idx % 50 == 0:
                save_progress(progress_file, progress)
                print(f"\n    [Checkpoint saved: {stats['success']} success, {stats['failed']} failed, {stats['quota_used']} quota used]\n")

            time.sleep(args.delay)

    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Saving progress...")
    except Exception as e:
        if 'quota' in str(e).lower():
            print(f"\n\nQuota exhausted! Saving progress...")
        else:
            print(f"\n\nError: {e}. Saving progress...")

    # Save final progress
    save_progress(progress_file, progress)

    # Save results to CSV
    if progress['results']:
        results_df = pd.DataFrame(progress['results'])
        results_df.to_csv(results_file, index=False)
        print(f"\nResults saved to: {results_file}")

    # Print summary
    print()
    print("=" * 70)
    print("VALIDATION SUMMARY")
    print("=" * 70)

    total_validated = len(progress['validated'])
    total_success = sum(1 for r in progress['results'] if r['success'])
    total_failed = sum(1 for r in progress['results'] if not r['success'])

    print(f"Total validated: {total_validated} / {len(urls)}")
    print(f"Success: {total_success} ({100*total_success/total_validated:.1f}%)" if total_validated else "")
    print(f"Failed: {total_failed} ({100*total_failed/total_validated:.1f}%)" if total_validated else "")
    print(f"Quota used this session: {stats['quota_used']} units")
    print()

    if total_validated < len(urls):
        print(f"Remaining: {len(urls) - total_validated} URLs")
        print("Resume with: python scripts/validate_channels.py --resume")

    # Show failed channels summary
    failed_results = [r for r in progress['results'] if not r['success']]
    if failed_results:
        print()
        print(f"Failed channels ({len(failed_results)}):")
        print("-" * 70)

        # Group by error type
        error_groups = {}
        for r in failed_results:
            error = r['error'] or 'Unknown'
            if error not in error_groups:
                error_groups[error] = []
            error_groups[error].append(r)

        for error, channels in sorted(error_groups.items(), key=lambda x: -len(x[1])):
            print(f"\n{error} ({len(channels)} channels):")
            for ch in channels[:5]:  # Show first 5
                print(f"  - {ch['brand_name'] or ch['domain']}: {ch['url']}")
            if len(channels) > 5:
                print(f"  ... and {len(channels) - 5} more")


if __name__ == '__main__':
    main()
