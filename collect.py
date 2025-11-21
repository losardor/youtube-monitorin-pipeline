#!/usr/bin/env python3
"""
Direct runner for the YouTube collector - simpler imports
"""
import sys
import os

# Get the directory containing this script
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

# Now we can import directly
import argparse
import logging
import yaml
from pathlib import Path
from datetime import datetime

# Import our modules
from src.youtube_client import YouTubeAPIClient
from src.database import Database
from src.utils.helpers import load_sources_from_csv, extract_channel_id_from_url, setup_logging, save_json

print("=" * 80)
print("YouTube Monitoring Pipeline - Data Collector")
print("=" * 80)

def main():
    parser = argparse.ArgumentParser(description='YouTube Data Collector')
    parser.add_argument('--sources', type=str, required=True,
                       help='Path to CSV file with source data')
    parser.add_argument('--max-channels', type=int, default=None,
                       help='Maximum number of channels to process (for testing)')
    parser.add_argument('--config', type=str, default='config/config.yaml',
                       help='Path to configuration file')
    
    args = parser.parse_args()
    
    print(f"\nConfiguration:")
    print(f"  Sources file: {args.sources}")
    print(f"  Max channels: {args.max_channels if args.max_channels else 'unlimited'}")
    print(f"  Config file: {args.config}")
    print()
    
    # Load configuration
    print("Loading configuration...")
    with open(args.config, 'r') as f:
        config = yaml.safe_load(f)
    
    # Setup logging
    log_config = config.get('logging', {})
    setup_logging(
        log_level=log_config.get('level', 'INFO'),
        log_file=log_config.get('log_file') if log_config.get('log_to_file') else None
    )
    
    print("✓ Configuration loaded")
    
    # Initialize API client
    print("Initializing YouTube API client...")
    api_key = config['api']['youtube_api_key']
    if api_key == "YOUR_YOUTUBE_API_KEY_HERE":
        print("✗ Error: Please set your YouTube API key in config.yaml")
        return 1
    
    youtube_client = YouTubeAPIClient(
        api_key=api_key,
        max_retries=config['api']['max_retries'],
        retry_delay=config['api']['retry_delay']
    )
    print("✓ API client initialized")
    
    # Initialize database
    print("Initializing database...")
    db_config = config.get('database', {})
    db = Database(db_path=db_config.get('sqlite_path', 'data/youtube_monitoring.db'))
    print("✓ Database initialized")
    
    # Load sources
    print(f"\nLoading sources from {args.sources}...")
    sources = load_sources_from_csv(args.sources)
    print(f"✓ Loaded {len(sources)} sources")
    
    if args.max_channels:
        sources = sources[:args.max_channels]
        print(f"✓ Limited to {args.max_channels} channels for testing")
    
    print()
    print("=" * 80)
    print("Starting collection...")
    print("=" * 80)
    print()
    
    # Start collection
    run_id = db.start_collection_run()
    
    stats = {
        'channels_processed': 0,
        'channels_success': 0,
        'channels_failed': 0,
        'videos_collected': 0,
        'comments_collected': 0,
        'quota_used': 0
    }
    
    collection_config = config.get('collection', {})
    output_config = config.get('output', {})
    
    for idx, source in enumerate(sources, 1):
        print(f"[{idx}/{len(sources)}] Processing: {source.get('brand_name', 'Unknown')}")
        print(f"         URL: {source.get('youtube_url', 'No URL')}")
        
        stats['channels_processed'] += 1
        
        # Extract channel ID
        channel_id = extract_channel_id_from_url(source.get('youtube_url', ''))
        if not channel_id:
            print("         ✗ Could not extract channel ID")
            stats['channels_failed'] += 1
            continue
        
        # Get channel info
        try:
            channel_info = youtube_client.get_channel_info(channel_id)
            if not channel_info:
                print("         ✗ Could not retrieve channel info")
                stats['channels_failed'] += 1
                continue
            
            print(f"         ✓ Found: {channel_info['snippet']['title']}")
            
            # Save channel
            if output_config.get('save_to_database', True):
                db.insert_channel(channel_info)
            
            stats['channels_success'] += 1
            
            # Get videos
            max_videos = collection_config.get('max_videos_per_channel', 50)
            videos = youtube_client.get_channel_videos(channel_info['id'], max_results=max_videos)
            
            if videos:
                print(f"         ✓ Found {len(videos)} videos")
                
                # Get video details
                video_ids = [v['video_id'] for v in videos]
                detailed_videos = youtube_client.get_video_details(video_ids)
                
                # Save videos
                for video in detailed_videos:
                    if output_config.get('save_to_database', True):
                        db.insert_video(video)
                
                stats['videos_collected'] += len(detailed_videos)
                
                # Get comments for first few videos
                max_comments = collection_config.get('max_comments_per_video', 100)
                for video in detailed_videos[:5]:  # Only first 5 videos to save quota
                    try:
                        comments = youtube_client.get_video_comments(video['id'], max_results=max_comments)
                        if comments and output_config.get('save_to_database', True):
                            db.insert_comments_batch(comments)
                        stats['comments_collected'] += len(comments)
                    except:
                        pass  # Comments might be disabled
            
            stats['quota_used'] = youtube_client.get_quota_usage()
            print(f"         Quota used so far: {stats['quota_used']} units")
            print()
            
        except Exception as e:
            print(f"         ✗ Error: {e}")
            stats['channels_failed'] += 1
    
    # Summary
    print()
    print("=" * 80)
    print("Collection Complete!")
    print("=" * 80)
    print(f"Channels processed: {stats['channels_processed']}")
    print(f"Channels successful: {stats['channels_success']}")
    print(f"Channels failed: {stats['channels_failed']}")
    print(f"Videos collected: {stats['videos_collected']}")
    print(f"Comments collected: {stats['comments_collected']}")
    print(f"Total quota used: {stats['quota_used']} units")
    print()
    
    # Save stats
    db.end_collection_run(run_id, {**stats, 'status': 'completed'})
    db.close()
    
    print("View your results with: python view_data.py --stats")
    print()
    
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nCollection interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
