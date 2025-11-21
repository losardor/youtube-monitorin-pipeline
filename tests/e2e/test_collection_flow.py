"""
End-to-end tests for the complete collection workflow
These tests are slow and should be run sparingly
"""
import pytest
import yaml
from pathlib import Path

from src.utils.helpers import load_sources_from_csv


@pytest.mark.e2e
@pytest.mark.slow
class TestCollectionFlow:
    """Test end-to-end collection workflows."""

    def test_config_loading(self, test_config_file):
        """Test configuration file loading."""
        with open(test_config_file) as f:
            config = yaml.safe_load(f)

        assert config is not None
        assert 'api' in config
        assert 'collection' in config
        assert config['api']['youtube_api_key'] == 'TEST_API_KEY_123'

    def test_csv_loading(self, test_csv_file):
        """Test loading sources from CSV."""
        sources = load_sources_from_csv(str(test_csv_file))

        assert len(sources) == 3
        assert sources[0]['youtube_url'] == 'https://www.youtube.com/@examplenews'
        assert sources[0]['domain'] == 'example.com'
        assert sources[0]['brand_name'] == 'Example News'

    def test_minimal_collection_workflow(self, test_csv_file, test_config_file, temp_dir):
        """Test minimal collection with mocked data.

        Note: This is a smoke test, not a real collection.
        Real e2e tests with API calls should be marked with @pytest.mark.api
        and made optional.
        """
        # Load config
        with open(test_config_file) as f:
            config = yaml.safe_load(f)

        # Load sources
        sources = load_sources_from_csv(str(test_csv_file))

        assert config is not None
        assert len(sources) > 0

        # Verify we have required configuration
        assert 'api' in config
        assert 'database' in config
        assert 'collection' in config

        # In a real e2e test, we would:
        # 1. Initialize YouTubeAPIClient
        # 2. Initialize Database
        # 3. Loop through sources
        # 4. Collect data for each channel
        # 5. Verify data in database
        # But we skip that here to avoid API quota usage


@pytest.mark.e2e
@pytest.mark.slow
class TestDataExport:
    """Test data export workflows."""

    def test_csv_export(self, populated_db, temp_dir):
        """Test exporting database to CSV."""
        import csv

        db = populated_db
        cursor = db.cursor

        # Export channels to CSV
        csv_file = temp_dir / 'channels_export.csv'

        cursor.execute("SELECT channel_id, channel_title, subscriber_count FROM channels")
        rows = cursor.fetchall()

        with open(csv_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['channel_id', 'channel_title', 'subscriber_count'])
            writer.writerows(rows)

        # Verify export
        assert csv_file.exists()

        with open(csv_file, 'r') as f:
            reader = csv.reader(f)
            lines = list(reader)
            assert len(lines) == 2  # Header + 1 data row
            assert lines[1][0] == 'UC_test123'

    def test_json_export(self, populated_db, temp_dir):
        """Test exporting database to JSON."""
        import json

        db = populated_db
        cursor = db.cursor

        # Export videos to JSON
        json_file = temp_dir / 'videos_export.json'

        cursor.execute("""
            SELECT video_id, title, view_count, like_count
            FROM videos
        """)

        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()

        videos = []
        for row in rows:
            video = dict(zip(columns, row))
            videos.append(video)

        with open(json_file, 'w') as f:
            json.dump(videos, f, indent=2)

        # Verify export
        assert json_file.exists()

        with open(json_file, 'r') as f:
            loaded = json.load(f)
            assert len(loaded) == 3
            assert all('video_id' in v for v in loaded)


@pytest.mark.e2e
@pytest.mark.slow
class TestErrorScenarios:
    """Test error handling in workflows."""

    def test_invalid_csv_path(self):
        """Test handling of invalid CSV path."""
        sources = load_sources_from_csv('/nonexistent/path/file.csv')
        assert sources == []

    def test_invalid_config_path(self):
        """Test handling of invalid config path."""
        with pytest.raises(FileNotFoundError):
            with open('/nonexistent/config.yaml') as f:
                yaml.safe_load(f)

    def test_malformed_csv(self, temp_dir):
        """Test handling of malformed CSV."""
        csv_file = temp_dir / 'malformed.csv'
        csv_file.write_text('Invalid,CSV\nData')

        sources = load_sources_from_csv(str(csv_file))
        # Should handle gracefully and return empty or partial data
        assert isinstance(sources, list)
