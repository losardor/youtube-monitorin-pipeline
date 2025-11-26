#!/usr/bin/env python3
"""
Test script to verify quota tracking fix
"""
import sys
import os
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

import yaml
from src.youtube_client import YouTubeAPIClient
from src.database import Database

def test_quota_tracking():
    """Test the quota tracking system"""
    print("Testing Quota Tracking Fix")
    print("=" * 50)

    # Load config
    with open('config/config_comprehensive.yaml') as f:
        config = yaml.safe_load(f)

    # Initialize database
    db = Database(db_path=config['database']['sqlite_path'])

    # Get last cumulative quota
    last_quota = db.get_last_quota_cumulative()
    print(f"Last cumulative quota from DB: {last_quota:,} units")

    # Start a test collection run
    run_id = db.start_collection_run()
    print(f"Started collection run ID: {run_id}")

    # Initialize YouTube client with cumulative quota
    youtube_client = YouTubeAPIClient(
        api_key=config['api']['youtube_api_key'],
        max_retries=config['api']['max_retries'],
        retry_delay=config['api']['retry_delay'],
        initial_quota=last_quota,
        db=db,
        run_id=run_id
    )

    print(f"YouTube client initialized with cumulative: {youtube_client.quota_cumulative:,} units")

    # Test a few API calls
    test_channel_ids = [
        'UC_x5XG1OV2P6uZZ5FSM9Ttw',  # Google Developers
        'UCBJycsmduvYEL83R_U4JriQ',  # MKBHD
    ]

    for idx, channel_id in enumerate(test_channel_ids, 1):
        print(f"\nTest {idx}: Getting channel info for {channel_id}")
        channel_info = youtube_client.get_channel_info(channel_id)
        if channel_info:
            print(f"  Channel: {channel_info['snippet']['title']}")
            print(f"  Session quota: {youtube_client.get_quota_usage()}")
            print(f"  Cumulative quota: {youtube_client.get_quota_cumulative()}")

            # Get a few videos to test quota tracking
            print(f"  Getting first 5 videos...")
            videos = youtube_client.get_channel_videos(channel_id, max_results=5)
            print(f"    Found {len(videos)} videos")
            print(f"    Session quota: {youtube_client.get_quota_usage()}")
            print(f"    Cumulative quota: {youtube_client.get_quota_cumulative()}")

    # End collection run
    stats = {
        'channels_processed': len(test_channel_ids),
        'videos_collected': 10,
        'comments_collected': 0,
        'quota_used': youtube_client.get_quota_usage(),
        'quota_cumulative': youtube_client.get_quota_cumulative(),
        'status': 'test_completed'
    }
    db.end_collection_run(run_id, stats)

    print("\n" + "=" * 50)
    print("Test Results:")
    print(f"Session quota used: {youtube_client.get_quota_usage()} units")
    print(f"Cumulative quota: {youtube_client.get_quota_cumulative()} units")
    print(f"Expected minimum quota: ~4 units (2 channel info + 2 video list calls)")

    # Check quota tracking details
    print("\nQuota Tracking Details:")
    db.cursor.execute("""
        SELECT api_method, COUNT(*) as calls, SUM(quota_cost) as total_cost
        FROM quota_tracking
        WHERE run_id = ?
        GROUP BY api_method
    """, (run_id,))

    for row in db.cursor.fetchall():
        print(f"  {row[0]}: {row[1]} calls, {row[2]} units")

    # Check the updated collection run
    db.cursor.execute("""
        SELECT quota_used, quota_cumulative
        FROM collection_runs
        WHERE run_id = ?
    """, (run_id,))

    row = db.cursor.fetchone()
    if row:
        print(f"\nDatabase Record:")
        print(f"  Session quota: {row[0]} units")
        print(f"  Cumulative quota: {row[1]} units")

    db.close()
    print("\n✓ Test completed successfully!")

if __name__ == "__main__":
    test_quota_tracking()