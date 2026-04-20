#!/usr/bin/env python3
"""
Fix URL issues in sources.csv:
1. Comma-separated URLs: Keep only the first valid URL
2. URL-encoded characters: Decode them
3. Trailing slashes and query parameters: Clean up
"""

import pandas as pd
from urllib.parse import unquote
from datetime import datetime
import re
import os

def get_first_youtube_url(url_string):
    """Extract the first valid YouTube URL from a comma-separated string"""
    if pd.isna(url_string) or str(url_string).strip() == '':
        return ''

    url_string = str(url_string).strip()

    # Split by comma
    urls = [u.strip() for u in url_string.split(',')]

    # Find first valid YouTube URL
    for url in urls:
        if 'youtube.com' in url.lower() or 'youtu.be' in url.lower():
            return url

    return url_string  # Return original if no YouTube URL found


def clean_url(url):
    """Clean a single URL"""
    if pd.isna(url) or str(url).strip() == '':
        return ''

    url = str(url).strip()

    # Skip non-YouTube URLs
    if 'youtube.com' not in url.lower() and 'youtu.be' not in url.lower():
        return url

    # Decode URL-encoded characters
    url = unquote(url)

    # Remove trailing slashes
    url = url.rstrip('/')

    # Remove query parameters (but keep the base URL)
    # Exception: keep playlist IDs
    if '?' in url and 'list=' not in url:
        url = url.split('?')[0]

    # Remove /featured, /videos, /about suffixes
    for suffix in ['/featured', '/videos', '/about', '/playlists']:
        if url.endswith(suffix):
            url = url[:-len(suffix)]

    return url


def fix_sources(input_path, output_path=None, dry_run=False):
    """Fix all URL issues in sources.csv"""

    print(f"Loading {input_path}...")
    df = pd.read_csv(input_path, encoding='utf-8')

    # Track changes
    changes = {
        'comma_fixed': 0,
        'decoded': 0,
        'cleaned': 0,
        'unchanged': 0
    }

    # Create a copy of the Youtube column
    original_urls = df['Youtube'].copy()

    # Process each URL
    for idx in range(len(df)):
        original = df.at[idx, 'Youtube']

        if pd.isna(original) or str(original).strip() == '':
            changes['unchanged'] += 1
            continue

        original = str(original).strip()

        # Step 1: Handle comma-separated URLs
        if ',' in original:
            new_url = get_first_youtube_url(original)
            changes['comma_fixed'] += 1
        else:
            new_url = original

        # Step 2: Clean the URL (decode, remove trailing slashes, etc.)
        cleaned_url = clean_url(new_url)

        # Track type of change
        if cleaned_url != original:
            if ',' in original:
                pass  # Already counted
            elif '%' in original and '%' not in cleaned_url:
                changes['decoded'] += 1
            else:
                changes['cleaned'] += 1
        else:
            changes['unchanged'] += 1

        # Apply the change
        df.at[idx, 'Youtube'] = cleaned_url

    # Print summary
    print("\n=== CHANGES SUMMARY ===")
    print(f"Comma-separated URLs fixed: {changes['comma_fixed']}")
    print(f"URL-encoded URLs decoded: {changes['decoded']}")
    print(f"URLs cleaned (trailing slashes, etc.): {changes['cleaned']}")
    print(f"Unchanged: {changes['unchanged']}")

    # Show sample changes
    print("\n=== SAMPLE CHANGES ===")
    sample_count = 0
    for idx in range(len(df)):
        orig = original_urls[idx] if pd.notna(original_urls[idx]) else ''
        new = df.at[idx, 'Youtube'] if pd.notna(df.at[idx, 'Youtube']) else ''

        if str(orig) != str(new) and orig:
            brand = df.at[idx, 'Brand Name'] if pd.notna(df.at[idx, 'Brand Name']) else df.at[idx, 'Domain']
            print(f"\n{brand}:")
            print(f"  Before: {str(orig)[:80]}...")
            print(f"  After:  {str(new)[:80]}")
            sample_count += 1
            if sample_count >= 10:
                break

    if dry_run:
        print("\n[DRY RUN - no changes saved]")
        return

    # Create backup
    backup_path = input_path.replace('.csv', f'_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv')
    print(f"\nCreating backup: {backup_path}")
    pd.read_csv(input_path, encoding='utf-8').to_csv(backup_path, index=False)

    # Save fixed file
    if output_path is None:
        output_path = input_path

    print(f"Saving fixed file: {output_path}")
    df.to_csv(output_path, index=False)

    # Verify
    print("\n=== VERIFICATION ===")
    df_new = pd.read_csv(output_path, encoding='utf-8')
    youtube_urls = df_new['Youtube'].dropna()
    youtube_urls = youtube_urls[youtube_urls.str.strip() != '']

    # Count remaining issues
    comma_remaining = sum(1 for u in youtube_urls if ',' in str(u))
    encoded_remaining = sum(1 for u in youtube_urls if '%' in str(u))

    print(f"Total YouTube URLs: {len(youtube_urls)}")
    print(f"Remaining comma-separated: {comma_remaining}")
    print(f"Remaining URL-encoded: {encoded_remaining}")

    print("\nDone!")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Fix URL issues in sources.csv')
    parser.add_argument('--input', default='data/sources.csv', help='Input CSV file')
    parser.add_argument('--output', help='Output CSV file (default: overwrite input)')
    parser.add_argument('--dry-run', action='store_true', help='Show changes without saving')
    args = parser.parse_args()

    # Get absolute path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(script_dir)
    input_path = os.path.join(parent_dir, args.input)
    output_path = os.path.join(parent_dir, args.output) if args.output else None

    fix_sources(input_path, output_path, args.dry_run)
