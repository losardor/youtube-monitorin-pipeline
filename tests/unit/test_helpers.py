"""
Unit tests for helper utility functions
"""
import pytest
import tempfile
from pathlib import Path
import json

from src.utils.helpers import (
    extract_channel_id_from_url,
    format_duration,
    clean_text,
    calculate_engagement_rate,
    categorize_video_length,
    save_json,
    load_json
)


# ============================================
# Tests for extract_channel_id_from_url
# ============================================

class TestExtractChannelId:
    """Test channel ID extraction from various URL formats."""

    def test_extract_from_channel_url(self):
        """Extract channel ID from /channel/ID format."""
        url = "https://www.youtube.com/channel/UC_test123"
        assert extract_channel_id_from_url(url) == "UC_test123"

    def test_extract_from_handle_url(self):
        """Extract handle from /@handle format."""
        url = "https://www.youtube.com/@testchannel"
        assert extract_channel_id_from_url(url) == "@testchannel"

    def test_extract_from_custom_url(self):
        """Extract from /c/customname format."""
        url = "https://www.youtube.com/c/mynewschannel"
        assert extract_channel_id_from_url(url) == "mynewschannel"

    def test_extract_from_user_url(self):
        """Extract from /user/username format."""
        url = "https://www.youtube.com/user/oldchannel"
        assert extract_channel_id_from_url(url) == "oldchannel"

    def test_handle_url_with_query_params(self):
        """Remove query parameters before extraction."""
        url = "https://www.youtube.com/@testchannel?ab_channel=Test"
        assert extract_channel_id_from_url(url) == "@testchannel"

    def test_handle_url_with_trailing_slash(self):
        """Handle URLs with trailing slashes."""
        url = "https://www.youtube.com/channel/UC_test123/"
        assert extract_channel_id_from_url(url) == "UC_test123"

    def test_empty_url(self):
        """Return None for empty URL."""
        assert extract_channel_id_from_url("") is None
        assert extract_channel_id_from_url("   ") is None

    def test_none_url(self):
        """Return None for None input."""
        assert extract_channel_id_from_url(None) is None

    def test_invalid_url(self):
        """Return None for invalid YouTube URL."""
        url = "https://www.example.com/not-youtube"
        assert extract_channel_id_from_url(url) is None


# ============================================
# Tests for format_duration
# ============================================

class TestFormatDuration:
    """Test duration formatting."""

    def test_format_seconds_only(self):
        """Format duration with only seconds."""
        assert format_duration(45) == "0:45"

    def test_format_minutes_and_seconds(self):
        """Format duration with minutes and seconds."""
        assert format_duration(154) == "2:34"

    def test_format_hours(self):
        """Format duration with hours."""
        assert format_duration(7215) == "2:00:15"

    def test_format_zero(self):
        """Format zero duration."""
        assert format_duration(0) == "0:00"

    def test_format_exact_hour(self):
        """Format exact hour."""
        assert format_duration(3600) == "1:00:00"

    def test_format_long_duration(self):
        """Format very long duration."""
        assert format_duration(10000) == "2:46:40"


# ============================================
# Tests for clean_text
# ============================================

class TestCleanText:
    """Test text cleaning function."""

    def test_remove_extra_whitespace(self):
        """Remove multiple spaces."""
        text = "This  has   extra    spaces"
        assert clean_text(text) == "This has extra spaces"

    def test_strip_whitespace(self):
        """Strip leading and trailing whitespace."""
        text = "  hello world  "
        assert clean_text(text) == "hello world"

    def test_handle_newlines(self):
        """Convert newlines to single spaces."""
        text = "Line1\nLine2\nLine3"
        assert clean_text(text) == "Line1 Line2 Line3"

    def test_handle_tabs(self):
        """Convert tabs to single spaces."""
        text = "Word1\t\tWord2"
        assert clean_text(text) == "Word1 Word2"

    def test_empty_string(self):
        """Return empty string for empty input."""
        assert clean_text("") == ""

    def test_none_input(self):
        """Return empty string for None."""
        assert clean_text(None) == ""

    def test_only_whitespace(self):
        """Return empty string for whitespace-only input."""
        assert clean_text("   \n\t  ") == ""


# ============================================
# Tests for calculate_engagement_rate
# ============================================

class TestCalculateEngagementRate:
    """Test engagement rate calculation."""

    def test_normal_engagement(self):
        """Calculate engagement rate with normal values."""
        video = {
            'view_count': 1000,
            'like_count': 50,
            'comment_count': 10
        }
        rate = calculate_engagement_rate(video)
        assert rate == 0.06  # (50 + 10) / 1000

    def test_zero_views(self):
        """Return 0 for zero views."""
        video = {
            'view_count': 0,
            'like_count': 10,
            'comment_count': 5
        }
        assert calculate_engagement_rate(video) == 0.0

    def test_high_engagement(self):
        """Handle high engagement rate."""
        video = {
            'view_count': 100,
            'like_count': 80,
            'comment_count': 20
        }
        assert calculate_engagement_rate(video) == 1.0

    def test_missing_fields(self):
        """Handle missing fields gracefully."""
        video = {}
        assert calculate_engagement_rate(video) == 0.0

    def test_string_values(self):
        """Convert string values to int."""
        video = {
            'view_count': '1000',
            'like_count': '100',
            'comment_count': '50'
        }
        assert calculate_engagement_rate(video) == 0.15


# ============================================
# Tests for categorize_video_length
# ============================================

class TestCategorizeVideoLength:
    """Test video length categorization."""

    def test_very_short(self):
        """Categorize very short videos (<1 min)."""
        assert categorize_video_length(30) == 'very_short'
        assert categorize_video_length(59) == 'very_short'

    def test_short(self):
        """Categorize short videos (1-5 min)."""
        assert categorize_video_length(60) == 'short'
        assert categorize_video_length(299) == 'short'

    def test_medium(self):
        """Categorize medium videos (5-20 min)."""
        assert categorize_video_length(300) == 'medium'
        assert categorize_video_length(1199) == 'medium'

    def test_long(self):
        """Categorize long videos (20-60 min)."""
        assert categorize_video_length(1200) == 'long'
        assert categorize_video_length(3599) == 'long'

    def test_very_long(self):
        """Categorize very long videos (>1 hour)."""
        assert categorize_video_length(3600) == 'very_long'
        assert categorize_video_length(10000) == 'very_long'

    def test_boundary_values(self):
        """Test exact boundary values."""
        assert categorize_video_length(60) == 'short'
        assert categorize_video_length(300) == 'medium'
        assert categorize_video_length(1200) == 'long'
        assert categorize_video_length(3600) == 'very_long'


# ============================================
# Tests for save_json and load_json
# ============================================

class TestJsonOperations:
    """Test JSON save and load operations."""

    def test_save_and_load_json(self, temp_dir):
        """Save and load JSON successfully."""
        data = {'key': 'value', 'number': 42, 'list': [1, 2, 3]}
        json_path = temp_dir / 'test.json'

        # Save
        assert save_json(data, str(json_path)) is True
        assert json_path.exists()

        # Load
        loaded = load_json(str(json_path))
        assert loaded == data

    def test_save_json_with_unicode(self, temp_dir):
        """Save JSON with unicode characters."""
        data = {'text': 'Hello 世界 🌍'}
        json_path = temp_dir / 'unicode.json'

        assert save_json(data, str(json_path)) is True

        loaded = load_json(str(json_path))
        assert loaded['text'] == 'Hello 世界 🌍'

    def test_load_nonexistent_file(self):
        """Return None for nonexistent file."""
        result = load_json('/nonexistent/path/file.json')
        assert result is None

    def test_save_to_invalid_path(self):
        """Return False for invalid save path."""
        data = {'key': 'value'}
        result = save_json(data, '/invalid/path/that/does/not/exist/file.json')
        assert result is False

    def test_load_invalid_json(self, temp_dir):
        """Return None for invalid JSON."""
        json_path = temp_dir / 'invalid.json'
        json_path.write_text('not valid json {]')

        result = load_json(str(json_path))
        assert result is None


# ============================================
# Parametrized Tests
# ============================================

@pytest.mark.parametrize("url,expected", [
    ("https://www.youtube.com/channel/UCtest", "UCtest"),
    ("https://youtube.com/@handle", "@handle"),
    ("http://www.youtube.com/c/custom", "custom"),  # HTTP
    ("https://m.youtube.com/user/mobile", "mobile"),  # Mobile
])
def test_various_url_formats(url, expected):
    """Test various URL format variations."""
    assert extract_channel_id_from_url(url) == expected


@pytest.mark.parametrize("seconds,expected", [
    (0, "0:00"),
    (30, "0:30"),
    (60, "1:00"),
    (90, "1:30"),
    (3600, "1:00:00"),
    (3661, "1:01:01"),
])
def test_duration_formats(seconds, expected):
    """Test various duration formats."""
    assert format_duration(seconds) == expected
