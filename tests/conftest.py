"""
Pytest configuration and shared fixtures
"""
import pytest
import tempfile
import os
import sys
from pathlib import Path
import json
import sqlite3

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import Database
from src.youtube_client import YouTubeAPIClient


# ============================================
# Database Fixtures
# ============================================

@pytest.fixture
def in_memory_db():
    """Provide an in-memory SQLite database for testing."""
    db = Database(db_path=":memory:")
    yield db
    db.close()


@pytest.fixture
def temp_db_file():
    """Provide a temporary database file that is cleaned up after test."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name

    yield db_path

    # Cleanup
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def populated_db(in_memory_db):
    """Provide a database populated with test data."""
    db = in_memory_db

    # Insert test channel
    test_channel = {
        'id': 'UC_test123',
        'snippet': {
            'title': 'Test Channel',
            'description': 'A test channel for testing',
            'customUrl': '@testchannel',
            'publishedAt': '2020-01-01T00:00:00Z',
            'country': 'US'
        },
        'statistics': {
            'subscriberCount': '10000',
            'videoCount': '100',
            'viewCount': '1000000'
        },
        'topicDetails': {
            'topicCategories': ['https://en.wikipedia.org/wiki/News']
        },
        'brandingSettings': {
            'channel': {
                'keywords': 'test news politics'
            }
        }
    }
    db.insert_channel(test_channel)

    # Insert test videos
    for i in range(3):
        test_video = {
            'id': f'video_{i}',
            'snippet': {
                'channelId': 'UC_test123',
                'title': f'Test Video {i}',
                'description': f'Description for video {i}',
                'publishedAt': f'2024-01-{i+1:02d}T00:00:00Z',
                'tags': ['test', 'video'],
                'categoryId': '25'
            },
            'contentDetails': {
                'duration': 'PT10M30S'
            },
            'statistics': {
                'viewCount': str(1000 * (i+1)),
                'likeCount': str(100 * (i+1)),
                'commentCount': str(10 * (i+1))
            }
        }
        db.insert_video(test_video)

    yield db


# ============================================
# File System Fixtures
# ============================================

@pytest.fixture
def temp_dir():
    """Provide a temporary directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def test_csv_file(temp_dir):
    """Create a test CSV file with sample channels."""
    csv_path = temp_dir / "test_sources.csv"

    csv_content = """Domain,Brand Name,Youtube,Rating,Orientation,Country,Language
example.com,Example News,https://www.youtube.com/@examplenews,T,Center,US,en
test.com,Test Channel,https://www.youtube.com/channel/UC_test123,M,Left,UK,en
demo.org,Demo News,https://www.youtube.com/c/demonews,H,Right,CA,en
"""

    csv_path.write_text(csv_content)
    yield csv_path


@pytest.fixture
def test_config_file(temp_dir):
    """Create a test configuration file."""
    config_path = temp_dir / "test_config.yaml"

    config_content = """
api:
  youtube_api_key: "TEST_API_KEY_123"
  max_retries: 3
  retry_delay: 1

collection:
  max_videos_per_channel: 5
  max_comments_per_video: 10
  video_order: "date"
  comment_order: "time"

database:
  type: "sqlite"
  sqlite_path: ":memory:"

logging:
  level: "WARNING"
  log_to_file: false

rate_limiting:
  enabled: true
  daily_quota: 10000
  quota_buffer: 1000

output:
  save_raw_json: false
  save_to_csv: false
  save_to_database: true
"""

    config_path.write_text(config_content)
    yield config_path


# ============================================
# API Response Fixtures
# ============================================

@pytest.fixture
def sample_channel_response():
    """Sample YouTube API channel response."""
    return {
        'kind': 'youtube#channelListResponse',
        'items': [{
            'kind': 'youtube#channel',
            'id': 'UC_sample123',
            'snippet': {
                'title': 'Sample Channel',
                'description': 'A sample channel for testing',
                'customUrl': '@samplechannel',
                'publishedAt': '2020-01-01T00:00:00Z',
                'country': 'US',
                'thumbnails': {
                    'default': {'url': 'https://example.com/thumb.jpg'}
                }
            },
            'contentDetails': {
                'relatedPlaylists': {
                    'uploads': 'UU_sample123'
                }
            },
            'statistics': {
                'viewCount': '1000000',
                'subscriberCount': '50000',
                'videoCount': '250'
            },
            'topicDetails': {
                'topicCategories': [
                    'https://en.wikipedia.org/wiki/News'
                ]
            },
            'brandingSettings': {
                'channel': {
                    'keywords': 'news politics current events'
                }
            }
        }]
    }


@pytest.fixture
def sample_video_response():
    """Sample YouTube API video response."""
    return {
        'kind': 'youtube#videoListResponse',
        'items': [{
            'kind': 'youtube#video',
            'id': 'video123',
            'snippet': {
                'channelId': 'UC_sample123',
                'title': 'Sample Video Title',
                'description': 'Sample video description',
                'publishedAt': '2024-01-15T10:00:00Z',
                'tags': ['news', 'politics', 'breaking'],
                'categoryId': '25',
                'defaultLanguage': 'en',
                'thumbnails': {
                    'default': {'url': 'https://example.com/video_thumb.jpg'}
                }
            },
            'contentDetails': {
                'duration': 'PT15M30S',
                'caption': 'true'
            },
            'statistics': {
                'viewCount': '50000',
                'likeCount': '2000',
                'commentCount': '150'
            }
        }]
    }


@pytest.fixture
def sample_comment_response():
    """Sample YouTube API comment thread response."""
    return {
        'kind': 'youtube#commentThreadListResponse',
        'items': [{
            'kind': 'youtube#commentThread',
            'id': 'comment123',
            'snippet': {
                'videoId': 'video123',
                'topLevelComment': {
                    'kind': 'youtube#comment',
                    'id': 'comment123',
                    'snippet': {
                        'textDisplay': 'This is a test comment',
                        'authorDisplayName': 'Test User',
                        'authorChannelId': {'value': 'UC_user123'},
                        'likeCount': 10,
                        'publishedAt': '2024-01-16T12:00:00Z',
                        'updatedAt': '2024-01-16T12:00:00Z'
                    }
                },
                'totalReplyCount': 2
            },
            'replies': {
                'comments': [{
                    'kind': 'youtube#comment',
                    'id': 'reply123',
                    'snippet': {
                        'textDisplay': 'This is a reply',
                        'authorDisplayName': 'Reply User',
                        'authorChannelId': {'value': 'UC_reply123'},
                        'parentId': 'comment123',
                        'likeCount': 5,
                        'publishedAt': '2024-01-16T13:00:00Z',
                        'updatedAt': '2024-01-16T13:00:00Z'
                    }
                }]
            }
        }]
    }


# ============================================
# Mock API Client
# ============================================

@pytest.fixture
def mock_youtube_client(mocker, sample_channel_response, sample_video_response, sample_comment_response):
    """Provide a mocked YouTube API client."""
    mock_client = mocker.Mock(spec=YouTubeAPIClient)
    mock_client.quota_usage = 0

    # Mock methods
    mock_client.get_channel_info.return_value = sample_channel_response['items'][0]
    mock_client.get_video_details.return_value = sample_video_response['items']
    mock_client.get_video_comments.return_value = sample_comment_response['items']

    return mock_client


# ============================================
# Pytest Configuration
# ============================================

def pytest_configure(config):
    """Configure pytest with custom settings."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "api: marks tests that require real API access"
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers automatically."""
    for item in items:
        # Add 'slow' marker to e2e tests
        if "e2e" in item.nodeid:
            item.add_marker(pytest.mark.slow)

        # Add 'api' marker to integration API tests
        if "api_integration" in item.nodeid:
            item.add_marker(pytest.mark.api)
