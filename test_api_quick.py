"""
Quick API test - bypasses the channel ID test
"""
import sys
import yaml
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from googleapiclient.discovery import build

print("="*60)
print("Quick API Test")
print("="*60)

# Load config
config_path = Path(__file__).parent / 'config' / 'config.yaml'
with open(config_path) as f:
    config = yaml.safe_load(f)

api_key = config['api']['youtube_api_key']

print(f"\nTesting API key...")
print(f"Key starts with: {api_key[:10]}...")

try:
    youtube = build('youtube', 'v3', developerKey=api_key)
    
    # Test with search
    request = youtube.search().list(
        part='snippet',
        q='news',
        type='channel',
        maxResults=1
    )
    
    response = request.execute()
    
    if response.get('items'):
        print("✓ API connection successful!")
        print(f"✓ API key is working properly!")
        print("\nYour API is ready. You can skip the full test and go directly to:")
        print("  python src/collector.py --sources data/sources.csv --max-channels 3")
    else:
        print("✗ No results returned")
        
except Exception as e:
    print(f"✗ Error: {e}")

print("\n" + "="*60)
