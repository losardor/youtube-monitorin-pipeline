#!/usr/bin/env python3
"""
Caption/Transcript Downloader for Collected Videos
Downloads transcripts for all videos that have captions available
"""
import sys
import os
from pathlib import Path

script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

import yaml
import time
from src.youtube_client import YouTubeAPIClient
from src.database import Database

def download_captions_for_collected_videos():
    """
    Download captions for all collected videos that have them available
    Uses the caption track IDs already in the database
    """
    
    print("=" * 80)
    print("Caption/Transcript Downloader")
    print("=" * 80)
    print()
    
    # Load config
    with open('config/config_comprehensive.yaml') as f:
        config = yaml.safe_load(f)
    
    # Initialize API client
    youtube_client = YouTubeAPIClient(
        api_key=config['api']['youtube_api_key'],
        max_retries=config['api']['max_retries'],
        retry_delay=config['api']['retry_delay']
    )
    
    # Connect to database
    db = Database('data/youtube_monitoring.db')
    cursor = db.conn.cursor()
    
    # Check caption availability
    print("Checking caption availability in database...")
    cursor.execute("""
        SELECT COUNT(DISTINCT video_id) 
        FROM caption_tracks
    """)
    videos_with_captions = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM videos")
    total_videos = cursor.fetchone()[0]
    
    print(f"Videos collected: {total_videos:,}")
    print(f"Videos with captions: {videos_with_captions:,} ({videos_with_captions/total_videos*100:.1f}%)")
    print()
    
    # Get caption tracks
    cursor.execute("""
        SELECT ct.caption_id, ct.video_id, ct.language, ct.track_kind, v.title
        FROM caption_tracks ct
        JOIN videos v ON ct.video_id = v.video_id
        WHERE ct.language IN ('en', 'it', 'de', 'fr', 'es')
        ORDER BY ct.video_id, 
                 CASE ct.language 
                     WHEN 'en' THEN 1 
                     WHEN 'it' THEN 2 
                     WHEN 'de' THEN 3 
                     WHEN 'fr' THEN 4 
                     ELSE 5 
                 END
    """)
    
    caption_tracks = cursor.fetchall()
    print(f"Caption tracks to download: {len(caption_tracks):,}")
    print()
    
    # Estimate time and quota
    estimated_time = len(caption_tracks) * 2  # 2 seconds per caption
    estimated_quota = len(caption_tracks) * 200  # Estimated quota cost
    
    print(f"Estimated time: {estimated_time/3600:.1f} hours")
    print(f"Estimated quota: {estimated_quota:,} units")
    print(f"  (Note: Caption downloads may have reduced/zero quota cost)")
    print()
    
    response = input("Start downloading captions? (y/n): ").lower()
    if response != 'y':
        print("Cancelled.")
        return
    
    # Create output directory
    caption_dir = Path('data/captions')
    caption_dir.mkdir(exist_ok=True)
    
    # Download captions
    downloaded = 0
    failed = 0
    
    print("\nDownloading captions...")
    print("=" * 80)
    
    for idx, (caption_id, video_id, language, track_kind, video_title) in enumerate(caption_tracks, 1):
        print(f"[{idx}/{len(caption_tracks)}] {video_title[:50]}... ({language})")
        
        try:
            # Download caption using API
            caption_response = youtube_client.youtube.captions().download(
                id=caption_id,
                tfmt='srt'  # or 'vtt', 'sbv'
            ).execute()
            
            # Save to file
            output_file = caption_dir / f"{video_id}_{language}.srt"
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(caption_response)
            
            # Update database
            cursor.execute("""
                UPDATE caption_tracks 
                SET downloaded = 1, 
                    download_path = ?,
                    downloaded_at = CURRENT_TIMESTAMP
                WHERE caption_id = ?
            """, (str(output_file), caption_id))
            db.conn.commit()
            
            downloaded += 1
            print(f"  ✓ Downloaded: {output_file.name}")
            
        except Exception as e:
            failed += 1
            print(f"  ✗ Failed: {e}")
        
        # Small delay
        time.sleep(1)
        
        # Progress update every 100
        if idx % 100 == 0:
            print(f"\nProgress: {downloaded} downloaded, {failed} failed")
            print(f"Quota used: {youtube_client.get_quota_usage():,} units\n")
    
    print("\n" + "=" * 80)
    print("Caption Download Complete")
    print("=" * 80)
    print(f"Downloaded: {downloaded:,}")
    print(f"Failed: {failed:,}")
    print(f"Total quota used: {youtube_client.get_quota_usage():,} units")
    print()
    
    db.close()

if __name__ == "__main__":
    # Check if caption metadata was collected
    db = Database('data/youtube_monitoring.db')
    cursor = db.conn.cursor()
    
    try:
        cursor.execute("SELECT COUNT(*) FROM caption_tracks")
        count = cursor.fetchone()[0]
        
        if count == 0:
            print("⚠ Warning: No caption tracks in database")
            print("Caption metadata was not collected during video collection")
            print("You need to:")
            print("1. Set collect_captions: true in config")
            print("2. Re-run collection OR run a separate caption metadata collection")
            sys.exit(1)
        
        download_captions_for_collected_videos()
        
    except Exception as e:
        print(f"Error: {e}")
        print("\nMake sure:")
        print("1. Database has caption_tracks table")
        print("2. Caption metadata was collected")
    finally:
        db.close()
