#!/usr/bin/env python3
"""
Validate the corrected URLs from problematic_urls_to_fix.csv
"""

import sys
import os
import time
import csv
from datetime import datetime

# Add parent directory to path
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
sys.path.insert(0, parent_dir)

import yaml
from src.youtube_client import YouTubeAPIClient
from src.utils.helpers import extract_channel_id_from_url


def load_config():
    """Load configuration"""
    config_path = os.path.join(parent_dir, 'config/config_comprehensive.yaml')
    with open(config_path) as f:
        return yaml.safe_load(f)


def validate_url(client, url):
    """Validate a single URL. Returns (success, channel_id, title, error)"""
    try:
        channel_id = extract_channel_id_from_url(url)
        if not channel_id:
            return False, None, None, "Could not extract channel ID"

        channel_info = client.get_channel_info(channel_id)

        if not channel_info:
            return False, channel_id, None, "Channel not found"

        title = channel_info.get('snippet', {}).get('title', 'Unknown')
        actual_id = channel_info.get('id', channel_id)
        return True, actual_id, title, None

    except Exception as e:
        error_msg = str(e)
        if 'quota' in error_msg.lower():
            raise
        return False, None, None, error_msg


def main():
    print("=" * 70)
    print("VALIDATING CORRECTED URLs")
    print("=" * 70)
    print()

    # Load problematic URLs
    input_file = os.path.join(parent_dir, 'data/problematic_urls_to_fix.csv')

    urls_to_validate = []
    with open(input_file, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            corrected = row.get('corrected_url', '').strip()
            if corrected and corrected != 'NONE':
                urls_to_validate.append({
                    'row_number': row['row_number'],
                    'domain': row['domain'],
                    'brand_name': row['brand_name'],
                    'original_url': row['current_url'],
                    'corrected_url': corrected,
                    'issue_type': row['issue_type']
                })

    # De-duplicate by corrected_url
    seen_urls = {}
    unique_urls = []
    for u in urls_to_validate:
        if u['corrected_url'] not in seen_urls:
            seen_urls[u['corrected_url']] = u
            unique_urls.append(u)

    print(f"Total entries with corrected URLs: {len(urls_to_validate)}")
    print(f"Unique corrected URLs to validate: {len(unique_urls)}")
    print()

    # Load config and initialize client
    config = load_config()
    client = YouTubeAPIClient(
        api_key=config['api']['youtube_api_key'],
        max_retries=3,
        retry_delay=2.0
    )

    # Validate each unique URL
    results = []
    success_count = 0
    failed_count = 0

    try:
        for idx, url_info in enumerate(unique_urls, 1):
            url = url_info['corrected_url']
            brand = url_info['brand_name'] or url_info['domain']

            print(f"[{idx}/{len(unique_urls)}] {brand[:35]:<35} ", end='', flush=True)

            success, channel_id, title, error = validate_url(client, url)

            result = {
                **url_info,
                'valid': success,
                'resolved_channel_id': channel_id,
                'channel_title': title,
                'error': error
            }
            results.append(result)

            if success:
                success_count += 1
                print(f"✓ {title[:30] if title else 'OK'}")
            else:
                failed_count += 1
                print(f"✗ {error[:40] if error else 'Failed'}")

            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\n\nInterrupted!")
    except Exception as e:
        print(f"\n\nError: {e}")

    # Print summary
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Validated: {len(results)} / {len(unique_urls)}")
    print(f"Success: {success_count}")
    print(f"Failed: {failed_count}")
    print()

    # Show failed ones
    failed = [r for r in results if not r['valid']]
    if failed:
        print("FAILED CORRECTED URLs:")
        print("-" * 70)
        for r in failed:
            print(f"  {r['domain']}: {r['corrected_url']}")
            print(f"    Error: {r['error']}")
        print()

    # Save results
    output_file = os.path.join(parent_dir, 'data/validation/corrected_urls_validation.csv')
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        fieldnames = ['row_number', 'domain', 'brand_name', 'original_url', 'corrected_url',
                      'issue_type', 'valid', 'resolved_channel_id', 'channel_title', 'error']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"Results saved to: {output_file}")


if __name__ == '__main__':
    main()
