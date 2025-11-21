"""
Test script to validate YouTube API setup and perform small test collection
"""

import sys
import yaml
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.youtube_client import YouTubeAPIClient
from src.utils.helpers import setup_logging, load_sources_from_csv


def test_api_connection(api_key: str) -> bool:
    """
    Test API connection and quota
    
    Args:
        api_key: YouTube API key
        
    Returns:
        True if connection successful
    """
    print("\n" + "="*60)
    print("Testing YouTube API Connection")
    print("="*60)
    
    try:
        client = YouTubeAPIClient(api_key)
        
        # Test with a well-known channel (YouTube Creators)
        test_channel_id = "UCkRfGP3d8Fb6NQJ0oS7TYfg"  # YouTube Creators channel
        
        print(f"\nAttempting to retrieve test channel: {test_channel_id}")
        channel_info = client.get_channel_info(test_channel_id)
        
        if channel_info:
            print("✓ API connection successful!")
            print(f"✓ Retrieved channel: {channel_info['snippet']['title']}")
            print(f"✓ Quota used so far: {client.get_quota_usage()} units")
            return True
        else:
            print("✗ Failed to retrieve channel information")
            return False
            
    except Exception as e:
        print(f"✗ API connection failed: {e}")
        return False


def test_source_loading(csv_path: str) -> bool:
    """
    Test loading sources from CSV
    
    Args:
        csv_path: Path to sources CSV
        
    Returns:
        True if successful
    """
    print("\n" + "="*60)
    print("Testing Source Loading")
    print("="*60)
    
    try:
        sources = load_sources_from_csv(csv_path)
        
        if sources:
            print(f"✓ Successfully loaded {len(sources)} sources from CSV")
            print(f"\nFirst 5 sources:")
            for i, source in enumerate(sources[:5], 1):
                print(f"  {i}. {source.get('brand_name', 'Unknown')} - {source.get('youtube_url', 'No URL')}")
            return True
        else:
            print("✗ No sources loaded from CSV")
            return False
            
    except Exception as e:
        print(f"✗ Failed to load sources: {e}")
        return False


def test_channel_resolution(api_key: str, sources: list, num_test: int = 3) -> bool:
    """
    Test resolving channel IDs from URLs
    
    Args:
        api_key: YouTube API key
        sources: List of source dictionaries
        num_test: Number of channels to test
        
    Returns:
        True if at least one successful
    """
    print("\n" + "="*60)
    print(f"Testing Channel Resolution ({num_test} channels)")
    print("="*60)
    
    try:
        client = YouTubeAPIClient(api_key)
        success_count = 0
        
        for i, source in enumerate(sources[:num_test], 1):
            url = source.get('youtube_url', '')
            brand = source.get('brand_name', 'Unknown')
            
            print(f"\n{i}. Testing: {brand}")
            print(f"   URL: {url}")
            
            channel_id = client.extract_channel_id(url)
            if not channel_id:
                print(f"   ✗ Could not extract channel ID from URL")
                continue
            
            print(f"   Channel identifier: {channel_id}")
            
            channel_info = client.get_channel_info(channel_id)
            if channel_info:
                print(f"   ✓ Successfully resolved to: {channel_info['snippet']['title']}")
                print(f"   Subscribers: {channel_info.get('statistics', {}).get('subscriberCount', 'Hidden')}")
                success_count += 1
            else:
                print(f"   ✗ Could not retrieve channel information")
        
        print(f"\n{'='*60}")
        print(f"Successfully resolved {success_count}/{num_test} channels")
        print(f"Quota used: {client.get_quota_usage()} units")
        
        return success_count > 0
        
    except Exception as e:
        print(f"✗ Channel resolution test failed: {e}")
        return False


def run_mini_collection(api_key: str, sources: list, num_channels: int = 2) -> bool:
    """
    Run a mini collection to test full pipeline
    
    Args:
        api_key: YouTube API key
        sources: List of source dictionaries
        num_channels: Number of channels to collect
        
    Returns:
        True if successful
    """
    print("\n" + "="*60)
    print(f"Running Mini Collection ({num_channels} channels)")
    print("="*60)
    
    try:
        from src.collector import YouTubeCollector
        
        # Create temporary config
        config = {
            'api': {
                'youtube_api_key': api_key,
                'max_retries': 3,
                'retry_delay': 2
            },
            'collection': {
                'max_videos_per_channel': 5,
                'max_comments_per_video': 10,
                'video_order': 'date',
                'comment_order': 'time',
                'collect_captions': False
            },
            'database': {
                'sqlite_path': 'data/test_youtube_monitoring.db'
            },
            'output': {
                'save_to_database': True,
                'save_raw_json': False,
                'save_to_csv': False
            },
            'logging': {
                'level': 'INFO',
                'log_to_file': False
            },
            'rate_limiting': {
                'enabled': True,
                'daily_quota': 10000,
                'quota_buffer': 1000
            }
        }
        
        # Save temporary config
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config, f)
            temp_config_path = f.name
        
        # Save temporary sources
        import pandas as pd
        temp_sources_df = pd.DataFrame(sources[:num_channels])
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            temp_sources_df.to_csv(f, index=False)
            temp_sources_path = f.name
        
        # Run collector
        collector = YouTubeCollector(config_path=temp_config_path)
        collector.run_collection(temp_sources_path, max_channels=num_channels)
        
        # Print results
        stats = collector.stats
        print("\n" + "="*60)
        print("Mini Collection Results")
        print("="*60)
        print(f"Channels processed: {stats['channels_processed']}")
        print(f"Channels successful: {stats['channels_success']}")
        print(f"Videos collected: {stats['videos_collected']}")
        print(f"Comments collected: {stats['comments_collected']}")
        print(f"Quota used: {stats['quota_used']} units")
        
        collector.close()
        
        # Cleanup temp files
        import os
        os.unlink(temp_config_path)
        os.unlink(temp_sources_path)
        
        return stats['channels_success'] > 0
        
    except Exception as e:
        print(f"✗ Mini collection failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main test runner"""
    setup_logging('INFO')
    
    print("\n" + "="*60)
    print("YouTube Monitoring Pipeline - Test Suite")
    print("="*60)
    
    # Load configuration
    config_path = Path(__file__).parent / 'config' / 'config.yaml'
    
    if not config_path.exists():
        print(f"\n✗ Configuration file not found: {config_path}")
        print("Please create config/config.yaml with your API key")
        return False
    
    with open(config_path) as f:
        config = yaml.safe_load(f)
    
    api_key = config['api']['youtube_api_key']
    
    if api_key == "YOUR_YOUTUBE_API_KEY_HERE":
        print("\n✗ Please set your YouTube API key in config/config.yaml")
        return False
    
    # Test 1: API Connection
    if not test_api_connection(api_key):
        print("\n✗ API connection test failed. Please check your API key.")
        return False
    
    # Test 2: Load sources
    sources_path = Path(__file__).parent / 'data' / 'sources.csv'
    if not sources_path.exists():
        print(f"\n✗ Sources file not found: {sources_path}")
        return False
    
    if not test_source_loading(str(sources_path)):
        print("\n✗ Source loading test failed.")
        return False
    
    # Load sources for remaining tests
    from src.utils.helpers import load_sources_from_csv
    sources = load_sources_from_csv(str(sources_path))
    
    if not sources:
        print("\n✗ No sources available for testing")
        return False
    
    # Test 3: Channel resolution
    if not test_channel_resolution(api_key, sources, num_test=3):
        print("\n⚠ Warning: Channel resolution had issues, but continuing...")
    
    # Test 4: Mini collection
    print("\n" + "="*60)
    print("Would you like to run a mini collection test?")
    print("This will collect data from 2 channels (5 videos each, 10 comments per video)")
    print("Estimated quota usage: ~50-100 units")
    print("="*60)
    response = input("Run mini collection? (y/n): ").strip().lower()
    
    if response == 'y':
        if not run_mini_collection(api_key, sources, num_channels=2):
            print("\n✗ Mini collection test failed.")
            return False
        print("\n✓ Mini collection successful!")
        print("Check data/test_youtube_monitoring.db for results")
    
    # All tests passed
    print("\n" + "="*60)
    print("✓ All Tests Passed!")
    print("="*60)
    print("\nYou're ready to run the full collection:")
    print("  python src/collector.py --sources data/sources.csv --max-channels 5")
    print("\nOr for full collection:")
    print("  python src/collector.py --sources data/sources.csv")
    
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)