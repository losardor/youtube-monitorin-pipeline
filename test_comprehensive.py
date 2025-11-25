#!/usr/bin/env python3
"""
Test comprehensive collection mode locally before server deployment
"""
import sys
import os

script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

import yaml

print("=" * 80)
print("Comprehensive Collection Mode - Local Test")
print("=" * 80)
print()

# Check config
print("1. Checking configuration...")
try:
    with open('config/config_comprehensive.yaml') as f:
        config = yaml.safe_load(f)
    
    api_key = config['api']['youtube_api_key']
    if api_key == "YOUR_YOUTUBE_API_KEY_HERE":
        print("   ✗ Please add your API key to config/config_comprehensive.yaml")
        sys.exit(1)
    
    print(f"   ✓ API key configured")
    print(f"   ✓ Max videos per channel: {config['collection']['max_videos_per_channel'] or 'UNLIMITED'}")
    print(f"   ✓ Max comments per video: {config['collection']['max_comments_per_video'] or 'UNLIMITED'}")
    print(f"   ✓ Quota limit: {config['rate_limiting']['daily_quota']:,} units")
    print()
except Exception as e:
    print(f"   ✗ Error loading config: {e}")
    sys.exit(1)

# Check source file
print("2. Checking source file...")
try:
    from src.utils.helpers import load_sources_from_csv
    sources = load_sources_from_csv('data/sources.csv')
    print(f"   ✓ Found {len(sources)} sources")
    print()
except Exception as e:
    print(f"   ✗ Error loading sources: {e}")
    sys.exit(1)

# Test API
print("3. Testing YouTube API connection...")
try:
    from googleapiclient.discovery import build
    youtube = build('youtube', 'v3', developerKey=api_key)
    
    # Simple test search
    request = youtube.search().list(part='snippet', q='news', type='channel', maxResults=1)
    response = request.execute()
    
    if response.get('items'):
        print(f"   ✓ API connection successful")
        print()
    else:
        print(f"   ⚠ API returned no results (but connection works)")
        print()
except Exception as e:
    print(f"   ✗ API connection failed: {e}")
    sys.exit(1)

# Estimate quota usage
print("4. Comprehensive Collection Estimates")
print("   Based on your current 31 channels with overview mode:")
print()
print("   Overview mode (current):")
print("     - Collected: 1,395 videos from 31 channels")
print("     - Average: ~45 videos per channel")
print("     - Comments: 535 (limited to first 5 videos)")
print("     - Quota: ~35 units per channel")
print()
print("   Comprehensive mode (projected):")
print("     - Expected: 100-5000 videos per channel (average ~500)")
print("     - Comments: ALL comments from ALL videos")
print("     - Quota: ~140 units per channel (3-4x more)")
print()
print("   For 3 test channels:")
print("     - Estimated videos: 300-1500")
print("     - Estimated comments: 5,000-50,000")
print("     - Estimated quota: 400-600 units")
print("     - Estimated time: 10-30 minutes")
print()

# Recommendations
print("5. Recommendations")
print()
print("   ✓ Configuration is ready")
print("   ✓ API connection works")
print("   ✓ Sources are loaded")
print()
print("   Ready to test! Run:")
print()
print("   python collect_comprehensive.py \\")
print("       --sources data/sources.csv \\")
print("       --max-channels 3")
print()
print("   This will:")
print("   - Collect ALL videos from 3 channels")
print("   - Collect ALL comments from all those videos")
print("   - Show you the difference from overview mode")
print("   - Use ~400-600 quota units")
print()
print("   After testing, compare with overview mode:")
print("   python view_data.py --stats")
print()
print("=" * 80)
print()

# Offer to run test
response = input("Would you like to run the test now with 3 channels? (y/n): ").strip().lower()

if response == 'y':
    print()
    print("Starting comprehensive collection test with 3 channels...")
    print("This will take 10-30 minutes. Press Ctrl+C to stop.")
    print()
    input("Press Enter to continue...")
    
    os.system('python collect_comprehensive.py --sources data/sources.csv --max-channels 3')
else:
    print()
    print("Test skipped. Run manually when ready:")
    print("  python collect_comprehensive.py --sources data/sources.csv --max-channels 3")
    print()
