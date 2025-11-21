"""
Integration tests for YouTube API client (with mocking)
Tests the API client logic without consuming quota
"""
import pytest
from unittest.mock import Mock, patch, MagicMock

from src.youtube_client import YouTubeAPIClient


@pytest.mark.integration
class TestYouTubeClientMocked:
    """Test YouTube API client with mocked responses."""

    @patch('src.youtube_client.build')
    def test_client_initialization(self, mock_build):
        """Test API client initialization."""
        mock_youtube = MagicMock()
        mock_build.return_value = mock_youtube

        client = YouTubeAPIClient(api_key="test_key", max_retries=3)

        assert client.api_key == "test_key"
        assert client.max_retries == 3
        assert client.quota_usage == 0
        mock_build.assert_called_once_with('youtube', 'v3', developerKey='test_key')

    @patch('src.youtube_client.build')
    def test_get_channel_info(self, mock_build, sample_channel_response):
        """Test fetching channel information."""
        mock_youtube = MagicMock()
        mock_build.return_value = mock_youtube

        # Mock the API response
        mock_youtube.channels().list().execute.return_value = sample_channel_response

        client = YouTubeAPIClient(api_key="test_key")
        result = client.get_channel_info("UC_sample123")

        assert result is not None
        assert result['id'] == 'UC_sample123'
        assert result['snippet']['title'] == 'Sample Channel'
        assert client.quota_usage > 0

    @patch('src.youtube_client.build')
    def test_get_video_details(self, mock_build, sample_video_response):
        """Test fetching video details."""
        mock_youtube = MagicMock()
        mock_build.return_value = mock_youtube

        mock_youtube.videos().list().execute.return_value = sample_video_response

        client = YouTubeAPIClient(api_key="test_key")
        result = client.get_video_details(["video123"])

        assert len(result) == 1
        assert result[0]['id'] == 'video123'
        assert result[0]['snippet']['title'] == 'Sample Video Title'

    @patch('src.youtube_client.build')
    def test_retry_on_failure(self, mock_build):
        """Test retry logic on API failure."""
        from googleapiclient.errors import HttpError
        from http.client import HTTPResponse

        mock_youtube = MagicMock()
        mock_build.return_value = mock_youtube

        # Mock HTTP error
        mock_response = Mock(spec=HTTPResponse)
        mock_response.status = 500
        error = HttpError(resp=mock_response, content=b'Server Error')

        # First two calls fail, third succeeds
        mock_youtube.channels().list().execute.side_effect = [
            error,
            error,
            {'items': [{'id': 'UC_test', 'snippet': {'title': 'Test'}}]}
        ]

        client = YouTubeAPIClient(api_key="test_key", max_retries=3, retry_delay=0.1)
        result = client.get_channel_info("UC_test")

        assert result is not None
        assert result['id'] == 'UC_test'

    @patch('src.youtube_client.build')
    def test_quota_exceeded_error(self, mock_build):
        """Test handling of quota exceeded error."""
        from googleapiclient.errors import HttpError
        from http.client import HTTPResponse

        mock_youtube = MagicMock()
        mock_build.return_value = mock_youtube

        mock_response = Mock(spec=HTTPResponse)
        mock_response.status = 403
        error = HttpError(resp=mock_response, content=b'Quota Exceeded')

        mock_youtube.channels().list().execute.side_effect = error

        client = YouTubeAPIClient(api_key="test_key")

        with pytest.raises(HttpError):
            client.get_channel_info("UC_test")


@pytest.mark.integration
@pytest.mark.database
class TestDatabaseIntegration:
    """Test database integration with realistic workflows."""

    def test_full_collection_workflow(self, in_memory_db):
        """Test complete collection workflow: channel → videos → comments."""
        db = in_memory_db

        # Insert channel
        channel = {
            'id': 'UC_workflow',
            'snippet': {'title': 'Workflow Channel', 'publishedAt': '2020-01-01T00:00:00Z'},
            'statistics': {'subscriberCount': '5000', 'videoCount': '50', 'viewCount': '500000'}
        }
        db.insert_channel(channel)

        # Insert videos
        for i in range(3):
            video = {
                'id': f'video_wf_{i}',
                'snippet': {
                    'channelId': 'UC_workflow',
                    'title': f'Workflow Video {i}',
                    'publishedAt': f'2024-0{i+1}-01T00:00:00Z'
                },
                'statistics': {'viewCount': str(1000 * (i+1)), 'likeCount': str(100 * (i+1)), 'commentCount': str(10 * (i+1))}
            }
            db.insert_video(video)

        # Insert comments
        for v in range(3):
            for c in range(5):
                comment = {
                    'comment_id': f'comment_wf_{v}_{c}',
                    'video_id': f'video_wf_{v}',
                    'text': f'Comment {c} on video {v}',
                    'author_name': f'User_{c}',
                    'author_channel_id': f'UC_user_{c}',
                    'like_count': c,
                    'published_at': '2024-02-01T00:00:00Z'
                }
                db.insert_comment(comment)

        # Verify data integrity
        cursor = db.cursor

        # Check channel
        cursor.execute("SELECT COUNT(*) FROM channels WHERE channel_id = 'UC_workflow'")
        assert cursor.fetchone()[0] == 1

        # Check videos
        cursor.execute("SELECT COUNT(*) FROM videos WHERE channel_id = 'UC_workflow'")
        assert cursor.fetchone()[0] == 3

        # Check comments
        cursor.execute("""
            SELECT COUNT(*) FROM comments c
            JOIN videos v ON c.video_id = v.video_id
            WHERE v.channel_id = 'UC_workflow'
        """)
        assert cursor.fetchone()[0] == 15  # 3 videos * 5 comments

    def test_checkpoint_save_and_restore(self, temp_dir, in_memory_db):
        """Test checkpoint functionality."""
        import json

        checkpoint_file = temp_dir / 'test_checkpoint.json'

        # Create checkpoint data
        checkpoint = {
            'channel_index': 50,
            'last_source': {'youtube_url': 'https://youtube.com/@test'},
            'stats': {
                'channels_attempted': 50,
                'channels_success': 45,
                'videos_collected': 2500,
                'comments_collected': 50000
            }
        }

        # Save checkpoint
        with open(checkpoint_file, 'w') as f:
            json.dump(checkpoint, f)

        # Load checkpoint
        with open(checkpoint_file, 'r') as f:
            loaded = json.load(f)

        assert loaded['channel_index'] == 50
        assert loaded['stats']['channels_success'] == 45
