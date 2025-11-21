#!/usr/bin/env python3
"""
Transcript Downloader using youtube-transcript-api
Works for any public video with captions/auto-captions
"""
import sys
import os
from pathlib import Path

script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

import time
import json
from src.database import Database

# Install: pip install youtube-transcript-api
try:
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound
except ImportError:
    print("ERROR: youtube-transcript-api not installed")
    print("Install with: pip install youtube-transcript-api")
    sys.exit(1)


def download_transcripts():
    """
    Download transcripts for all collected videos
    Uses youtube-transcript-api (unofficial but reliable)
    """
    
    print("=" * 80)
    print("YouTube Transcript Downloader")
    print("=" * 80)
    print()
    print("⚠ IMPORTANT NOTES:")
    print("  - This uses an unofficial API (web scraping)")
    print("  - No quota limits, no authentication needed")
    print("  - Works for public videos with captions/auto-captions")
    print("  - Used widely in research but technically against ToS")
    print("=" * 80)
    print()
    
    # Connect to database
    db = Database('data/youtube_monitoring.db')
    cursor = db.conn.cursor()
    
    # Get all videos
    print("Loading videos from database...")
    cursor.execute("""
        SELECT video_id, title, channel_id
        FROM videos
        ORDER BY video_id
    """)
    videos = cursor.fetchall()
    
    print(f"Total videos: {len(videos):,}")
    print()
    
    # Check if transcript table exists, create if not
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transcripts (
            video_id TEXT PRIMARY KEY,
            language TEXT,
            transcript_text TEXT,
            transcript_json TEXT,
            downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (video_id) REFERENCES videos(video_id)
        )
    """)
    db.conn.commit()
    
    # Check how many already downloaded
    cursor.execute("SELECT COUNT(*) FROM transcripts")
    already_done = cursor.fetchone()[0]
    
    if already_done > 0:
        print(f"Already downloaded: {already_done:,} transcripts")
        response = input("Continue and skip existing? (y/n): ").lower()
        if response != 'y':
            print("Cancelled.")
            return
        print()
    
    # Language preferences (in order)
    languages = ['en', 'it', 'de', 'fr', 'es']
    
    # Statistics
    stats = {
        'downloaded': 0,
        'skipped': 0,
        'no_transcript': 0,
        'disabled': 0,
        'errors': 0
    }
    
    # Create output directory for JSON files
    transcript_dir = Path('data/transcripts')
    transcript_dir.mkdir(exist_ok=True)
    
    print("Starting download...")
    print("=" * 80)
    print()
    
    for idx, (video_id, title, channel_id) in enumerate(videos, 1):
        # Skip if already downloaded
        cursor.execute("SELECT 1 FROM transcripts WHERE video_id = ?", (video_id,))
        if cursor.fetchone():
            stats['skipped'] += 1
            if idx % 100 == 0:
                print(f"[{idx}/{len(videos)}] Skipped (already downloaded)")
            continue
        
        print(f"[{idx}/{len(videos)}] {title[:60]}...")
        
        try:
            # Try to get transcript in preferred language order
            transcript = None
            used_language = None
            
            for lang in languages:
                try:
                    transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=[lang])
                    used_language = lang
                    break
                except NoTranscriptFound:
                    continue
            
            # If no preferred language, try getting any available
            if not transcript:
                try:
                    transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
                    # Get first available transcript
                    first_transcript = next(iter(transcript_list))
                    transcript = first_transcript.fetch()
                    used_language = first_transcript.language_code
                except:
                    raise NoTranscriptFound(video_id)
            
            if transcript:
                # Combine into full text
                full_text = " ".join([entry['text'] for entry in transcript])
                
                # Save to database
                cursor.execute("""
                    INSERT INTO transcripts (video_id, language, transcript_text, transcript_json)
                    VALUES (?, ?, ?, ?)
                """, (video_id, used_language, full_text, json.dumps(transcript)))
                db.conn.commit()
                
                # Also save JSON to file
                output_file = transcript_dir / f"{video_id}_{used_language}.json"
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump({
                        'video_id': video_id,
                        'language': used_language,
                        'transcript': transcript,
                        'full_text': full_text
                    }, f, ensure_ascii=False, indent=2)
                
                stats['downloaded'] += 1
                print(f"  ✓ Downloaded ({used_language}): {len(transcript)} segments, {len(full_text)} chars")
            
        except TranscriptsDisabled:
            stats['disabled'] += 1
            print(f"  ⚠ Transcripts disabled")
            
        except NoTranscriptFound:
            stats['no_transcript'] += 0
            print(f"  ⚠ No transcript available")
            
        except Exception as e:
            stats['errors'] += 1
            print(f"  ✗ Error: {e}")
        
        # Small delay to be respectful
        time.sleep(0.5)
        
        # Progress update every 100
        if idx % 100 == 0:
            print()
            print(f"Progress: {stats['downloaded']:,} downloaded, "
                  f"{stats['no_transcript']:,} no transcript, "
                  f"{stats['disabled']:,} disabled, "
                  f"{stats['errors']:,} errors")
            print()
    
    # Final summary
    print()
    print("=" * 80)
    print("Transcript Download Complete")
    print("=" * 80)
    print(f"Total videos processed: {len(videos):,}")
    print(f"Successfully downloaded: {stats['downloaded']:,}")
    print(f"Skipped (already done): {stats['skipped']:,}")
    print(f"No transcript available: {stats['no_transcript']:,}")
    print(f"Transcripts disabled: {stats['disabled']:,}")
    print(f"Errors: {stats['errors']:,}")
    print()
    print(f"Success rate: {stats['downloaded']/(len(videos)-stats['skipped'])*100:.1f}%")
    print()
    print(f"Transcripts saved to: {transcript_dir}")
    print(f"Database table: transcripts")
    print()
    
    db.close()


if __name__ == "__main__":
    download_transcripts()
