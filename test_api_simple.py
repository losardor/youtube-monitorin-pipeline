from googleapiclient.discovery import build
import yaml

# Load config
with open('config/config.yaml') as f:
    config = yaml.safe_load(f)

api_key = config['api']['youtube_api_key']

print(f"Testing API key: {api_key[:10]}...{api_key[-5:]}")
print(f"Key length: {len(api_key)} characters (should be 39)")

# Try to build the client
try:
    youtube = build('youtube', 'v3', developerKey=api_key)
    print("✓ YouTube client created successfully")
    
    # Simple request: channels.list by handle costs 1 unit, where the
    # search.list this replaces cost 100.
    request = youtube.channels().list(
        part='snippet',
        forHandle='@YouTube'
    )
    
    response = request.execute()
    
    if response.get('items'):
        print("✓ API request successful! (cost: 1 unit)")
        print(f"✓ Found channel: {response['items'][0]['snippet']['title']}")
    else:
        print("✗ API request returned no results")
        
except Exception as e:
    print(f"✗ Error: {e}")
    print("\nCommon causes:")
    print("1. API key is invalid or not activated")
    print("2. YouTube Data API v3 is not enabled")
    print("3. API key restrictions are too strict")
    print("4. Billing needs to be enabled")
