#!/usr/bin/env python3
"""
Apply URL corrections from problematic_urls_to_fix.csv to sources.csv
"""

import pandas as pd
import sys
from datetime import datetime

def apply_corrections():
    # Load files
    corrections_file = 'data/problematic_urls_to_fix.csv'
    sources_file = 'data/sources.csv'

    print(f"Loading corrections from {corrections_file}...")
    corrections = pd.read_csv(corrections_file)

    print(f"Loading sources from {sources_file}...")
    sources = pd.read_csv(sources_file)

    # Check for empty corrections
    empty_corrections = corrections[corrections['corrected_url'].isna() | (corrections['corrected_url'] == '')]
    if len(empty_corrections) > 0:
        print(f"\nWARNING: {len(empty_corrections)} entries have no corrected_url!")
        print("Please complete all corrections before running this script.")
        print("\nMissing corrections:")
        for _, row in empty_corrections.iterrows():
            print(f"  Row {row['row_number']}: {row['brand_name']} ({row['issue_type']})")

        response = input("\nContinue anyway? (y/n): ")
        if response.lower() != 'y':
            print("Aborted.")
            return

    # Create backup
    backup_file = f"data/sources_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    sources.to_csv(backup_file, index=False)
    print(f"\nBackup created: {backup_file}")

    # Apply corrections
    updates = 0
    cleared = 0
    skipped = 0

    for _, correction in corrections.iterrows():
        row_num = int(correction['row_number']) - 2  # Convert to 0-indexed (minus header)
        corrected_url = correction['corrected_url']

        if pd.isna(corrected_url) or corrected_url == '':
            skipped += 1
            continue

        if row_num < 0 or row_num >= len(sources):
            print(f"  WARNING: Row {correction['row_number']} out of range, skipping")
            skipped += 1
            continue

        if corrected_url.upper() == 'NONE':
            # Clear the YouTube URL
            sources.at[row_num, 'Youtube'] = ''
            cleared += 1
        else:
            # Update with corrected URL
            old_url = sources.at[row_num, 'Youtube']
            sources.at[row_num, 'Youtube'] = corrected_url
            updates += 1

    # Save updated sources
    sources.to_csv(sources_file, index=False)

    print(f"\nCorrections applied:")
    print(f"  Updated: {updates}")
    print(f"  Cleared (NONE): {cleared}")
    print(f"  Skipped: {skipped}")
    print(f"\nSources file updated: {sources_file}")

    # Verify
    print("\n--- Verification ---")
    sources_new = pd.read_csv(sources_file)
    youtube_urls = sources_new['Youtube'].dropna()
    youtube_urls = youtube_urls[youtube_urls != '']
    print(f"Total rows with YouTube URLs: {len(youtube_urls)}")

if __name__ == '__main__':
    apply_corrections()
