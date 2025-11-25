#!/usr/bin/env python3
"""
Comprehensive YouTube Data Collector
Collects ALL available data (no limits) with checkpointing and resume capability
"""
import sys
import os
import json
import time
from datetime import datetime
from pathlib import Path

# Setup path
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

import argparse
import yaml
from src.youtube_client import YouTubeAPIClient
from src.database import Database
from src.utils.helpers import load_sources_from_csv, extract_channel_id_from_url, setup_logging

class ComprehensiveCollector:
    """Comprehensive data collector with checkpointing"""
    
    def __init__(self, config_path='config/config_comprehensive.yaml'):
        # Load config
        with open(config_path) as f:
            self.config = yaml.safe_load(f)
        
        # Setup logging
        log_config = self.config.get('logging', {})
        setup_logging(
            log_level=log_config.get('level', 'INFO'),
            log_file=log_config.get('log_file')
        )
        
        # Initialize components
        self.youtube_client = YouTubeAPIClient(
            api_key=self.config['api']['youtube_api_key'],
            max_retries=self.config['api']['max_retries'],
            retry_delay=self.config['api']['retry_delay']
        )
        
        db_path = self.config['database']['sqlite_path']
        self.db = Database(db_path=db_path)
        
        # Collection settings
        self.collection_config = self.config.get('collection', {})
        self.output_config = self.config.get('output', {})
        self.error_config = self.config.get('error_handling', {})
        
        # Stats
        self.stats = {
            'channels_processed': 0,
            'channels_success': 0,
            'channels_failed': 0,
            'videos_collected': 0,
            'comments_collected': 0,
            'quota_used': 0,
            'start_time': datetime.now().isoformat(),
            'consecutive_failures': 0
        }
        
        # Checkpoint management
        self.checkpoint_dir = Path(self.output_config.get('checkpoint_path', 'data/checkpoints'))
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        
        print("✓ Comprehensive Collector initialized")
    
    def save_checkpoint(self, channel_index, source):
        """Save progress checkpoint"""
        checkpoint = {
            'channel_index': channel_index,
            'last_source': source,
            'stats': self.stats,
            'timestamp': datetime.now().isoformat()
        }
        
        checkpoint_file = self.checkpoint_dir / 'latest_checkpoint.json'
        with open(checkpoint_file, 'w') as f:
            json.dump(checkpoint, f, indent=2)
    
    def load_checkpoint(self):
        """Load checkpoint if exists"""
        checkpoint_file = self.checkpoint_dir / 'latest_checkpoint.json'
        if checkpoint_file.exists():
            with open(checkpoint_file) as f:
                return json.load(f)
        return None
    
    def collect_all_videos(self, channel_id):
        """Collect ALL videos from a channel (no limit)"""
        print(f"      Collecting ALL videos from channel...")
        videos = []
        page_count = 0
        
        try:
            # Get channel info for uploads playlist
            channel_info = self.youtube_client.get_channel_info(channel_id)
            if not channel_info:
                return []
            
            uploads_playlist = channel_info['contentDetails']['relatedPlaylists']['uploads']
            next_page_token = None
            
            while True:
                # Get playlist page
                request_params = {
                    'part': 'snippet,contentDetails',
                    'playlistId': uploads_playlist,
                    'maxResults': 50
                }
                if next_page_token:
                    request_params['pageToken'] = next_page_token
                
                response = self.youtube_client.youtube.playlistItems().list(**request_params).execute()
                
                page_items = response.get('items', [])
                video_ids = [item['contentDetails']['videoId'] for item in page_items]
                
                if video_ids:
                    # Get detailed video info
                    detailed = self.youtube_client.get_video_details(video_ids)
                    videos.extend(detailed)
                    
                    # Save to database immediately
                    for video in detailed:
                        if self.output_config.get('save_to_database', True):
                            self.db.insert_video(video)
                
                page_count += 1
                print(f"      Videos collected: {len(videos)} (page {page_count})", end='\r')
                
                next_page_token = response.get('nextPageToken')
                if not next_page_token:
                    break
                
                # Small delay between pages
                time.sleep(0.3)
            
            print(f"      Videos collected: {len(videos)} (COMPLETE)")
            return videos
            
        except Exception as e:
            print(f"      ✗ Error collecting videos: {e}")
            return videos
    
    def collect_all_comments(self, video_id):
        """Collect ALL comments from a video (no limit)"""
        comments = []
        page_count = 0
        next_page_token = None
        
        try:
            while True:
                request_params = {
                    'part': 'snippet,replies',
                    'videoId': video_id,
                    'maxResults': 100,
                    'order': self.collection_config.get('comment_order', 'time'),
                    'textFormat': 'plainText'
                }
                if next_page_token:
                    request_params['pageToken'] = next_page_token
                
                response = self.youtube_client.youtube.commentThreads().list(**request_params).execute()
                
                for item in response.get('items', []):
                    # Top-level comment
                    top_comment = item['snippet']['topLevelComment']['snippet']
                    comment_data = {
                        'comment_id': item['snippet']['topLevelComment']['id'],
                        'video_id': video_id,
                        'text': top_comment['textDisplay'],
                        'author': top_comment['authorDisplayName'],
                        'author_channel_id': top_comment.get('authorChannelId', {}).get('value'),
                        'like_count': top_comment['likeCount'],
                        'published_at': top_comment['publishedAt'],
                        'updated_at': top_comment['updatedAt'],
                        'parent_id': None,
                        'reply_count': item['snippet']['totalReplyCount']
                    }
                    comments.append(comment_data)
                    
                    # Add replies
                    if 'replies' in item:
                        for reply in item['replies']['comments']:
                            reply_snippet = reply['snippet']
                            reply_data = {
                                'comment_id': reply['id'],
                                'video_id': video_id,
                                'text': reply_snippet['textDisplay'],
                                'author': reply_snippet['authorDisplayName'],
                                'author_channel_id': reply_snippet.get('authorChannelId', {}).get('value'),
                                'like_count': reply_snippet['likeCount'],
                                'published_at': reply_snippet['publishedAt'],
                                'updated_at': reply_snippet['updatedAt'],
                                'parent_id': comment_data['comment_id'],
                                'reply_count': 0
                            }
                            comments.append(reply_data)
                
                page_count += 1
                
                next_page_token = response.get('nextPageToken')
                if not next_page_token:
                    break
                
                # Delay between comment pages
                delay = self.collection_config.get('delay_between_comment_pages', 1.0)
                time.sleep(delay)
            
            # Save all comments at once
            if comments and self.output_config.get('save_to_database', True):
                self.db.insert_comments_batch(comments)
            
            return comments
            
        except Exception as e:
            # Comments might be disabled
            if "commentsDisabled" in str(e) or "forbidden" in str(e).lower():
                return []
            print(f"        ✗ Error collecting comments: {e}")
            return comments
    
    def collect_channel(self, source, index, total):
        """Collect all data for a single channel"""
        print(f"\n[{index}/{total}] {source.get('brand_name', 'Unknown')}")
        print(f"    URL: {source.get('youtube_url', 'No URL')}")
        
        try:
            # Extract channel ID
            channel_id = extract_channel_id_from_url(source.get('youtube_url', ''))
            if not channel_id:
                print("    ✗ Could not extract channel ID")
                return False
            
            # Get channel info
            channel_info = self.youtube_client.get_channel_info(channel_id)
            if not channel_info:
                print("    ✗ Could not retrieve channel info")
                return False
            
            print(f"    ✓ Channel: {channel_info['snippet']['title']}")
            print(f"    Subscribers: {channel_info.get('statistics', {}).get('subscriberCount', 'Hidden')}")
            
            # Save channel
            if self.output_config.get('save_to_database', True):
                self.db.insert_channel(channel_info)
            
            # Collect ALL videos
            videos = self.collect_all_videos(channel_info['id'])
            self.stats['videos_collected'] += len(videos)
            
            if not videos:
                print("    ⚠ No videos found")
                return True
            
            # Collect comments from ALL videos
            print(f"    Collecting comments from {len(videos)} videos...")
            video_comments = 0
            
            for vid_idx, video in enumerate(videos, 1):
                comments = self.collect_all_comments(video['id'])
                video_comments += len(comments)
                
                if (vid_idx % 10) == 0 or vid_idx == len(videos):
                    print(f"      Progress: {vid_idx}/{len(videos)} videos, {video_comments} comments", end='\r')
                
                # Small delay between videos
                delay = self.collection_config.get('delay_between_videos', 0.5)
                time.sleep(delay)
            
            print(f"      Progress: {len(videos)}/{len(videos)} videos, {video_comments} comments (COMPLETE)")
            self.stats['comments_collected'] += video_comments
            
            # Update quota
            self.stats['quota_used'] = self.youtube_client.get_quota_usage()
            print(f"    Quota used: {self.stats['quota_used']:,} units")
            
            # Reset consecutive failures
            self.stats['consecutive_failures'] = 0
            
            return True
            
        except Exception as e:
            print(f"    ✗ Error: {e}")
            self.stats['consecutive_failures'] += 1
            return False
    
    def run(self, sources_csv, start_from=0, max_channels=None, resume=False):
        """Run comprehensive collection"""
        print("=" * 80)
        print("COMPREHENSIVE DATA COLLECTION - NO LIMITS")
        print("=" * 80)
        print()
        
        # Check for resume
        checkpoint = None
        if resume:
            checkpoint = self.load_checkpoint()
            if checkpoint:
                print(f"✓ Resuming from checkpoint at channel {checkpoint['channel_index']}")
                start_from = checkpoint['channel_index']
                self.stats = checkpoint['stats']
        
        # Load sources
        print(f"Loading sources from {sources_csv}...")
        sources = load_sources_from_csv(sources_csv)
        print(f"✓ Loaded {len(sources)} sources")
        
        # Apply start and limit
        if start_from > 0:
            sources = sources[start_from:]
            print(f"✓ Starting from channel {start_from}")
        
        if max_channels:
            sources = sources[:max_channels]
            print(f"✓ Limited to {max_channels} channels")
        
        print()
        print("=" * 80)
        print(f"Starting collection of {len(sources)} channels...")
        print("Press Ctrl+C to pause and save checkpoint")
        print("=" * 80)
        
        # Start database run
        run_id = self.db.start_collection_run()
        
        try:
            for idx, source in enumerate(sources, start=start_from + 1):
                self.stats['channels_processed'] += 1
                
                # Collect channel
                success = self.collect_channel(source, idx, start_from + len(sources))
                
                if success:
                    self.stats['channels_success'] += 1
                else:
                    self.stats['channels_failed'] += 1
                
                # Check consecutive failures
                max_failures = self.error_config.get('max_consecutive_failures', 5)
                if self.stats['consecutive_failures'] >= max_failures:
                    print(f"\n⚠ Stopping: {max_failures} consecutive failures")
                    break
                
                # Save checkpoint every N channels
                checkpoint_interval = self.output_config.get('checkpoint_every_n_channels', 10)
                if self.stats['channels_processed'] % checkpoint_interval == 0:
                    self.save_checkpoint(idx, source)
                    print(f"\n    ✓ Checkpoint saved")
                
                # Check quota
                rate_config = self.config.get('rate_limiting', {})
                if rate_config.get('enabled', True):
                    daily_quota = rate_config.get('daily_quota', 1000000)
                    quota_buffer = rate_config.get('quota_buffer', 50000)
                    
                    if self.stats['quota_used'] >= (daily_quota - quota_buffer):
                        print(f"\n⚠ Approaching quota limit ({self.stats['quota_used']:,} / {daily_quota:,})")
                        print("  Stopping to preserve buffer")
                        break
                
                # Delay between channels
                delay = self.collection_config.get('delay_between_channels', 2.0)
                time.sleep(delay)
            
            # Summary
            print("\n" + "=" * 80)
            print("COLLECTION COMPLETE")
            print("=" * 80)
            print(f"Channels processed: {self.stats['channels_processed']}")
            print(f"Channels successful: {self.stats['channels_success']}")
            print(f"Channels failed: {self.stats['channels_failed']}")
            print(f"Videos collected: {self.stats['videos_collected']:,}")
            print(f"Comments collected: {self.stats['comments_collected']:,}")
            print(f"Total quota used: {self.stats['quota_used']:,} units")
            print()
            
            # Save final stats
            self.db.end_collection_run(run_id, {**self.stats, 'status': 'completed'})
            
        except KeyboardInterrupt:
            print("\n\n⚠ Collection interrupted by user")
            print("Saving checkpoint...")
            self.save_checkpoint(idx if 'idx' in locals() else start_from, 
                               source if 'source' in locals() else {})
            self.db.end_collection_run(run_id, {**self.stats, 'status': 'interrupted'})
            print("✓ Checkpoint saved. Resume with --resume flag")
            
        except Exception as e:
            print(f"\n✗ Fatal error: {e}")
            import traceback
            traceback.print_exc()
            self.db.end_collection_run(run_id, {**self.stats, 'status': 'failed', 'error': str(e)})
        
        finally:
            self.db.close()

def main():
    parser = argparse.ArgumentParser(description='Comprehensive YouTube Data Collector')
    parser.add_argument('--sources', type=str, required=True,
                       help='Path to CSV file with source data')
    parser.add_argument('--config', type=str, default='config/config_comprehensive.yaml',
                       help='Path to configuration file')
    parser.add_argument('--start-from', type=int, default=0,
                       help='Start from channel N (for resuming)')
    parser.add_argument('--max-channels', type=int, default=None,
                       help='Limit collection to N channels')
    parser.add_argument('--resume', action='store_true',
                       help='Resume from last checkpoint')
    
    args = parser.parse_args()
    
    collector = ComprehensiveCollector(config_path=args.config)
    collector.run(
        sources_csv=args.sources,
        start_from=args.start_from,
        max_channels=args.max_channels,
        resume=args.resume
    )

if __name__ == "__main__":
    main()
