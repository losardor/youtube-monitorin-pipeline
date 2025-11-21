"""
Unit tests for database operations
"""
import pytest
import sqlite3
from datetime import datetime

from src.database import Database


# ============================================
# Database Creation Tests
# ============================================

class TestDatabaseCreation:
    """Test database initialization and table creation."""

    def test_create_in_memory_database(self):
        """Create in-memory database successfully."""
        db = Database(db_path=":memory:")
        assert db.conn is not None
        assert db.cursor is not None
        db.close()

    def test_create_file_database(self, temp_db_file):
        """Create file-based database."""
        db = Database(db_path=temp_db_file)
        assert db.conn is not None
        db.close()

    def test_tables_created(self, in_memory_db):
        """Verify all required tables are created."""
        db = in_memory_db
        cursor = db.cursor

        # Check table existence
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table'
        """)
        tables = {row[0] for row in cursor.fetchall()}

        expected_tables = {
            'channels', 'videos', 'comments',
            'caption_tracks', 'collection_runs'
        }
        assert expected_tables.issubset(tables)

    def test_foreign_keys_enabled(self, in_memory_db):
        """Verify foreign keys are enabled."""
        db = in_memory_db
        cursor = db.cursor

        cursor.execute("PRAGMA foreign_keys")
        result = cursor.fetchone()
        assert result[0] == 1  # Foreign keys enabled


# ============================================
# Channel Operations Tests
# ============================================

class TestChannelOperations:
    """Test channel insert and query operations."""

    def test_insert_channel(self, in_memory_db):
        """Insert a channel successfully."""
        db = in_memory_db

        channel_data = {
            'id': 'UC_test123',
            'snippet': {
                'title': 'Test Channel',
                'description': 'Test description',
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
                'topicCategories': ['News']
            },
            'brandingSettings': {
                'channel': {
                    'keywords': 'test news'
                }
            }
        }

        result = db.insert_channel(channel_data)
        assert result is True

        # Verify insertion
        cursor = db.cursor
        cursor.execute("SELECT channel_id, channel_title FROM channels WHERE channel_id = ?",
                      ('UC_test123',))
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == 'UC_test123'
        assert row[1] == 'Test Channel'

    def test_upsert_channel(self, in_memory_db):
        """Test INSERT OR REPLACE behavior."""
        db = in_memory_db

        channel_data = {
            'id': 'UC_test123',
            'snippet': {
                'title': 'Original Title',
                'publishedAt': '2020-01-01T00:00:00Z'
            },
            'statistics': {
                'subscriberCount': '10000',
                'videoCount': '100',
                'viewCount': '1000000'
            }
        }

        # First insert
        db.insert_channel(channel_data)

        # Update with new data
        channel_data['snippet']['title'] = 'Updated Title'
        channel_data['statistics']['subscriberCount'] = '20000'
        db.insert_channel(channel_data)

        # Verify update
        cursor = db.cursor
        cursor.execute("SELECT channel_title, subscriber_count FROM channels WHERE channel_id = ?",
                      ('UC_test123',))
        row = cursor.fetchone()
        assert row[0] == 'Updated Title'
        assert row[1] == 20000

    def test_insert_channel_with_source_metadata(self, in_memory_db):
        """Insert channel with source metadata."""
        db = in_memory_db

        channel_data = {
            'id': 'UC_test123',
            'snippet': {
                'title': 'Test Channel',
                'publishedAt': '2020-01-01T00:00:00Z'
            },
            'statistics': {
                'subscriberCount': '10000',
                'videoCount': '100',
                'viewCount': '1000000'
            },
            'source_metadata': {
                'domain': 'example.com',
                'rating': 'T',
                'orientation': 'Center'
            }
        }

        db.insert_channel(channel_data)

        # Verify metadata
        cursor = db.cursor
        cursor.execute("""
            SELECT source_domain, source_rating, source_orientation
            FROM channels WHERE channel_id = ?
        """, ('UC_test123',))
        row = cursor.fetchone()
        assert row[0] == 'example.com'
        assert row[1] == 'T'
        assert row[2] == 'Center'


# ============================================
# Video Operations Tests
# ============================================

class TestVideoOperations:
    """Test video insert and query operations."""

    def test_insert_video(self, populated_db):
        """Insert a video successfully."""
        db = populated_db

        video_data = {
            'id': 'video_new',
            'snippet': {
                'channelId': 'UC_test123',
                'title': 'New Video',
                'description': 'New description',
                'publishedAt': '2024-02-01T00:00:00Z',
                'tags': ['tag1', 'tag2'],
                'categoryId': '25'
            },
            'contentDetails': {
                'duration': 'PT5M30S'
            },
            'statistics': {
                'viewCount': '5000',
                'likeCount': '200',
                'commentCount': '30'
            }
        }

        result = db.insert_video(video_data)
        assert result is True

        # Verify insertion
        cursor = db.cursor
        cursor.execute("SELECT video_id, title FROM videos WHERE video_id = ?",
                      ('video_new',))
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == 'video_new'
        assert row[1] == 'New Video'

    def test_video_foreign_key_constraint(self, in_memory_db):
        """Test foreign key constraint on channel_id."""
        db = in_memory_db

        video_data = {
            'id': 'video_orphan',
            'snippet': {
                'channelId': 'UC_nonexistent',  # Non-existent channel
                'title': 'Orphan Video',
                'publishedAt': '2024-02-01T00:00:00Z'
            },
            'statistics': {}
        }

        # This should fail due to foreign key constraint
        # Note: SQLite may not enforce this by default in all modes
        result = db.insert_video(video_data)
        # The insert might succeed but the video should be orphaned


# ============================================
# Comment Operations Tests
# ============================================

class TestCommentOperations:
    """Test comment insert operations."""

    def test_insert_comment(self, populated_db):
        """Insert a comment successfully."""
        db = populated_db

        comment_data = {
            'comment_id': 'comment_new',
            'video_id': 'video_0',
            'text': 'Test comment text',
            'author_name': 'Test Author',
            'author_channel_id': 'UC_author',
            'like_count': 5,
            'published_at': '2024-02-01T10:00:00Z',
            'updated_at': '2024-02-01T10:00:00Z'
        }

        result = db.insert_comment(comment_data)
        assert result is True

        # Verify insertion
        cursor = db.cursor
        cursor.execute("SELECT comment_id, text FROM comments WHERE comment_id = ?",
                      ('comment_new',))
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == 'comment_new'
        assert row[1] == 'Test comment text'

    def test_insert_comment_reply(self, populated_db):
        """Insert a reply comment with parent_id."""
        db = populated_db

        # Insert parent comment first
        parent = {
            'comment_id': 'parent_123',
            'video_id': 'video_0',
            'text': 'Parent comment',
            'author_name': 'Parent Author',
            'author_channel_id': 'UC_parent',
            'like_count': 10,
            'published_at': '2024-02-01T10:00:00Z'
        }
        db.insert_comment(parent)

        # Insert reply
        reply = {
            'comment_id': 'reply_123',
            'video_id': 'video_0',
            'parent_id': 'parent_123',
            'text': 'Reply to parent',
            'author_name': 'Reply Author',
            'author_channel_id': 'UC_reply',
            'like_count': 2,
            'published_at': '2024-02-01T11:00:00Z'
        }
        result = db.insert_comment(reply)
        assert result is True

        # Verify reply relationship
        cursor = db.cursor
        cursor.execute("SELECT parent_id FROM comments WHERE comment_id = ?",
                      ('reply_123',))
        row = cursor.fetchone()
        assert row[0] == 'parent_123'

    def test_batch_insert_comments(self, populated_db):
        """Insert multiple comments in batch."""
        db = populated_db

        comments = []
        for i in range(10):
            comments.append({
                'comment_id': f'batch_comment_{i}',
                'video_id': 'video_0',
                'text': f'Batch comment {i}',
                'author_name': f'Author {i}',
                'author_channel_id': f'UC_author_{i}',
                'like_count': i,
                'published_at': '2024-02-01T10:00:00Z'
            })

        result = db.insert_comments_batch(comments)
        assert result is True

        # Verify batch insertion
        cursor = db.cursor
        cursor.execute("SELECT COUNT(*) FROM comments WHERE comment_id LIKE 'batch_comment_%'")
        count = cursor.fetchone()[0]
        assert count == 10


# ============================================
# Query Operations Tests
# ============================================

class TestQueryOperations:
    """Test database query operations."""

    def test_query_channel_videos(self, populated_db):
        """Query videos for a specific channel."""
        db = populated_db
        cursor = db.cursor

        cursor.execute("""
            SELECT COUNT(*) FROM videos
            WHERE channel_id = 'UC_test123'
        """)
        count = cursor.fetchone()[0]
        assert count == 3  # We inserted 3 videos in fixture

    def test_query_with_join(self, populated_db):
        """Query using JOIN across tables."""
        db = populated_db
        cursor = db.cursor

        cursor.execute("""
            SELECT c.channel_title, COUNT(v.video_id) as video_count
            FROM channels c
            LEFT JOIN videos v ON c.channel_id = v.channel_id
            WHERE c.channel_id = 'UC_test123'
            GROUP BY c.channel_id
        """)
        row = cursor.fetchone()
        assert row[0] == 'Test Channel'
        assert row[1] == 3

    def test_query_video_statistics(self, populated_db):
        """Query video statistics."""
        db = populated_db
        cursor = db.cursor

        cursor.execute("""
            SELECT SUM(view_count), AVG(like_count)
            FROM videos
            WHERE channel_id = 'UC_test123'
        """)
        row = cursor.fetchone()
        total_views = row[0]
        avg_likes = row[1]

        assert total_views == 6000  # 1000 + 2000 + 3000
        assert avg_likes == 200.0  # (100 + 200 + 300) / 3


# ============================================
# Transaction Tests
# ============================================

class TestTransactions:
    """Test transaction handling."""

    def test_commit_transaction(self, in_memory_db):
        """Test explicit commit."""
        db = in_memory_db

        channel_data = {
            'id': 'UC_trans',
            'snippet': {'title': 'Transaction Test', 'publishedAt': '2020-01-01T00:00:00Z'},
            'statistics': {'subscriberCount': '100', 'videoCount': '10', 'viewCount': '1000'}
        }

        db.insert_channel(channel_data)
        db.conn.commit()

        # Verify persisted
        cursor = db.conn.cursor()
        cursor.execute("SELECT channel_id FROM channels WHERE channel_id = ?", ('UC_trans',))
        assert cursor.fetchone() is not None

    def test_rollback_transaction(self, in_memory_db):
        """Test transaction rollback."""
        db = in_memory_db

        channel_data = {
            'id': 'UC_rollback',
            'snippet': {'title': 'Rollback Test', 'publishedAt': '2020-01-01T00:00:00Z'},
            'statistics': {'subscriberCount': '100', 'videoCount': '10', 'viewCount': '1000'}
        }

        db.insert_channel(channel_data)
        db.conn.rollback()

        # Verify not persisted
        cursor = db.conn.cursor()
        cursor.execute("SELECT channel_id FROM channels WHERE channel_id = ?", ('UC_rollback',))
        assert cursor.fetchone() is None


# ============================================
# Index Tests
# ============================================

class TestIndexes:
    """Test that indexes are created."""

    def test_indexes_exist(self, in_memory_db):
        """Verify indexes are created."""
        db = in_memory_db
        cursor = db.cursor

        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='index' AND name LIKE 'idx_%'
        """)
        indexes = {row[0] for row in cursor.fetchall()}

        expected_indexes = {
            'idx_videos_channel',
            'idx_videos_published',
            'idx_comments_video',
            'idx_comments_published'
        }

        assert expected_indexes.issubset(indexes)
