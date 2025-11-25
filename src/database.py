"""
Database Module for YouTube Monitoring Pipeline
Handles data persistence using SQLite or PostgreSQL
"""

import sqlite3
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime
import json

logger = logging.getLogger(__name__)


class Database:
    """Database handler for YouTube monitoring data"""
    
    def __init__(self, db_path: str = "data/youtube_monitoring.db"):
        """
        Initialize database connection
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.conn = None
        self.cursor = None
        self._connect()
        self._create_tables()
        
    def _connect(self):
        """Establish database connection"""
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.cursor = self.conn.cursor()
            # Enable foreign keys
            self.cursor.execute("PRAGMA foreign_keys = ON")
            logger.info(f"Connected to database: {self.db_path}")
        except Exception as e:
            logger.error(f"Error connecting to database: {e}")
            raise
    
    def _create_tables(self):
        """Create database tables if they don't exist"""
        try:
            # Channels table
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS channels (
                    channel_id TEXT PRIMARY KEY,
                    channel_url TEXT,
                    channel_title TEXT,
                    description TEXT,
                    custom_url TEXT,
                    published_at TEXT,
                    country TEXT,
                    subscriber_count INTEGER,
                    video_count INTEGER,
                    view_count INTEGER,
                    topic_categories TEXT,  -- JSON array
                    keywords TEXT,
                    branding_keywords TEXT,
                    first_collected_at TEXT,
                    last_updated_at TEXT,
                    source_domain TEXT,
                    source_rating TEXT,
                    source_orientation TEXT,
                    UNIQUE(channel_id)
                )
            """)
            
            # Videos table
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS videos (
                    video_id TEXT PRIMARY KEY,
                    channel_id TEXT,
                    title TEXT,
                    description TEXT,
                    published_at TEXT,
                    duration TEXT,
                    duration_seconds INTEGER,
                    category_id TEXT,
                    category_name TEXT,
                    default_language TEXT,
                    default_audio_language TEXT,
                    view_count INTEGER,
                    like_count INTEGER,
                    comment_count INTEGER,
                    tags TEXT,  -- JSON array
                    topic_categories TEXT,  -- JSON array
                    made_for_kids BOOLEAN,
                    has_captions BOOLEAN,
                    caption_languages TEXT,  -- JSON array
                    thumbnail_url TEXT,
                    collected_at TEXT,
                    FOREIGN KEY (channel_id) REFERENCES channels (channel_id),
                    UNIQUE(video_id)
                )
            """)
            
            # Comments table
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS comments (
                    comment_id TEXT PRIMARY KEY,
                    video_id TEXT,
                    parent_id TEXT,
                    author_name TEXT,
                    author_channel_id TEXT,
                    text TEXT,
                    like_count INTEGER,
                    reply_count INTEGER,
                    published_at TEXT,
                    updated_at TEXT,
                    collected_at TEXT,
                    FOREIGN KEY (video_id) REFERENCES videos (video_id),
                    FOREIGN KEY (parent_id) REFERENCES comments (comment_id),
                    UNIQUE(comment_id)
                )
            """)
            
            # Captions metadata table
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS caption_tracks (
                    caption_id TEXT PRIMARY KEY,
                    video_id TEXT,
                    language TEXT,
                    language_name TEXT,
                    track_kind TEXT,
                    is_auto_generated BOOLEAN,
                    collected_at TEXT,
                    FOREIGN KEY (video_id) REFERENCES videos (video_id),
                    UNIQUE(caption_id)
                )
            """)
            
            # Collection runs table (for tracking)
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS collection_runs (
                    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    start_time TEXT,
                    end_time TEXT,
                    channels_processed INTEGER,
                    videos_collected INTEGER,
                    comments_collected INTEGER,
                    quota_used INTEGER,
                    quota_cumulative INTEGER DEFAULT 0,  -- Total quota including resumed sessions
                    status TEXT,
                    error_message TEXT
                )
            """)

            # Add quota_cumulative column if it doesn't exist (for existing databases)
            self.cursor.execute("""
                PRAGMA table_info(collection_runs)
            """)
            columns = [col[1] for col in self.cursor.fetchall()]
            if 'quota_cumulative' not in columns:
                self.cursor.execute("""
                    ALTER TABLE collection_runs
                    ADD COLUMN quota_cumulative INTEGER DEFAULT 0
                """)

            # Quota tracking table for detailed API call tracking
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS quota_tracking (
                    track_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER,
                    timestamp TEXT,
                    api_method TEXT,
                    quota_cost INTEGER,
                    details TEXT,
                    FOREIGN KEY (run_id) REFERENCES collection_runs (run_id)
                )
            """)
            
            # Create indexes for common queries
            self.cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_videos_channel 
                ON videos(channel_id)
            """)
            
            self.cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_videos_published 
                ON videos(published_at)
            """)
            
            self.cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_comments_video 
                ON comments(video_id)
            """)
            
            self.cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_comments_published 
                ON comments(published_at)
            """)
            
            self.conn.commit()
            logger.info("Database tables created/verified")
            
        except Exception as e:
            logger.error(f"Error creating tables: {e}")
            raise
    
    def insert_channel(self, channel_data: Dict) -> bool:
        """
        Insert or update channel data
        
        Args:
            channel_data: Dictionary containing channel information
            
        Returns:
            True if successful, False otherwise
        """
        try:
            snippet = channel_data.get('snippet', {})
            statistics = channel_data.get('statistics', {})
            branding = channel_data.get('brandingSettings', {}).get('channel', {})
            source_metadata = channel_data.get('source_metadata', {})

            self.cursor.execute("""
                INSERT OR REPLACE INTO channels (
                    channel_id, channel_url, channel_title, description, custom_url,
                    published_at, country, subscriber_count, video_count, view_count,
                    topic_categories, keywords, branding_keywords, last_updated_at,
                    source_domain, source_rating, source_orientation
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                channel_data['id'],
                f"https://www.youtube.com/channel/{channel_data['id']}",
                snippet.get('title'),
                snippet.get('description'),
                snippet.get('customUrl'),
                snippet.get('publishedAt'),
                snippet.get('country'),
                int(statistics.get('subscriberCount', 0)) if statistics.get('subscriberCount') else None,
                int(statistics.get('videoCount', 0)) if statistics.get('videoCount') else None,
                int(statistics.get('viewCount', 0)) if statistics.get('viewCount') else None,
                json.dumps(channel_data.get('topicDetails', {}).get('topicCategories', [])),
                branding.get('keywords'),
                json.dumps(branding.get('keywords', '').split() if branding.get('keywords') else []),
                datetime.utcnow().isoformat(),
                source_metadata.get('domain'),
                source_metadata.get('rating'),
                source_metadata.get('orientation')
            ))
            
            self.conn.commit()
            logger.debug(f"Inserted/updated channel: {channel_data['id']}")
            return True
            
        except Exception as e:
            logger.error(f"Error inserting channel: {e}")
            self.conn.rollback()
            return False
    
    def insert_video(self, video_data: Dict) -> bool:
        """
        Insert or update video data
        
        Args:
            video_data: Dictionary containing video information
            
        Returns:
            True if successful, False otherwise
        """
        try:
            snippet = video_data.get('snippet', {})
            statistics = video_data.get('statistics', {})
            content_details = video_data.get('contentDetails', {})
            status = video_data.get('status', {})
            
            # Parse duration to seconds
            duration_seconds = None
            duration_str = content_details.get('duration')
            if duration_str:
                try:
                    import isodate
                    duration_seconds = int(isodate.parse_duration(duration_str).total_seconds())
                except:
                    pass
            
            self.cursor.execute("""
                INSERT OR REPLACE INTO videos (
                    video_id, channel_id, title, description, published_at,
                    duration, duration_seconds, category_id, default_language,
                    default_audio_language, view_count, like_count, comment_count,
                    tags, topic_categories, made_for_kids, has_captions,
                    thumbnail_url, collected_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                video_data['id'],
                snippet.get('channelId'),
                snippet.get('title'),
                snippet.get('description'),
                snippet.get('publishedAt'),
                content_details.get('duration'),
                duration_seconds,
                snippet.get('categoryId'),
                snippet.get('defaultLanguage'),
                snippet.get('defaultAudioLanguage'),
                int(statistics.get('viewCount', 0)) if statistics.get('viewCount') else None,
                int(statistics.get('likeCount', 0)) if statistics.get('likeCount') else None,
                int(statistics.get('commentCount', 0)) if statistics.get('commentCount') else None,
                json.dumps(snippet.get('tags', [])),
                json.dumps(video_data.get('topicDetails', {}).get('topicCategories', [])),
                status.get('madeForKids'),
                content_details.get('caption') == 'true',
                snippet.get('thumbnails', {}).get('high', {}).get('url'),
                datetime.utcnow().isoformat()
            ))
            
            self.conn.commit()
            logger.debug(f"Inserted/updated video: {video_data['id']}")
            return True
            
        except Exception as e:
            logger.error(f"Error inserting video: {e}")
            self.conn.rollback()
            return False
    
    def insert_comment(self, comment_data: Dict) -> bool:
        """
        Insert or update comment data

        Args:
            comment_data: Dictionary containing comment information
                Required: comment_id, video_id, text
                Optional: parent_id, author_name, author_channel_id, like_count,
                         reply_count, published_at, updated_at

        Returns:
            True if successful, False otherwise
        """
        try:
            # Support both 'author' and 'author_name' field names
            author = comment_data.get('author_name') or comment_data.get('author', '')

            self.cursor.execute("""
                INSERT OR REPLACE INTO comments (
                    comment_id, video_id, parent_id, author_name, author_channel_id,
                    text, like_count, reply_count, published_at, updated_at, collected_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                comment_data['comment_id'],
                comment_data['video_id'],
                comment_data.get('parent_id'),
                author,
                comment_data.get('author_channel_id'),
                comment_data['text'],
                comment_data.get('like_count', 0),
                comment_data.get('reply_count', 0),
                comment_data.get('published_at'),
                comment_data.get('updated_at'),
                datetime.utcnow().isoformat()
            ))

            self.conn.commit()
            return True

        except Exception as e:
            logger.error(f"Error inserting comment: {e}")
            self.conn.rollback()
            return False
    
    def insert_comments_batch(self, comments: List[Dict]) -> bool:
        """
        Insert multiple comments in a batch

        Args:
            comments: List of comment dictionaries

        Returns:
            True if all comments were inserted successfully, False otherwise
        """
        if not comments:
            return True

        success_count = 0

        try:
            for comment in comments:
                if self.insert_comment(comment):
                    success_count += 1

            logger.info(f"Inserted {success_count}/{len(comments)} comments")
            return success_count == len(comments)

        except Exception as e:
            logger.error(f"Error in batch comment insert: {e}")
            return False
    
    def insert_caption_track(self, caption_data: Dict, video_id: str) -> bool:
        """
        Insert caption track metadata
        
        Args:
            caption_data: Dictionary containing caption track information
            video_id: Associated video ID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            snippet = caption_data.get('snippet', {})
            
            self.cursor.execute("""
                INSERT OR REPLACE INTO caption_tracks (
                    caption_id, video_id, language, language_name,
                    track_kind, is_auto_generated, collected_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                caption_data['id'],
                video_id,
                snippet.get('language'),
                snippet.get('name'),
                snippet.get('trackKind'),
                snippet.get('audioTrackType') == 'primary',
                datetime.utcnow().isoformat()
            ))
            
            self.conn.commit()
            return True
            
        except Exception as e:
            logger.error(f"Error inserting caption track: {e}")
            self.conn.rollback()
            return False
    
    def start_collection_run(self) -> int:
        """
        Start a new collection run and return its ID
        
        Returns:
            Collection run ID
        """
        try:
            self.cursor.execute("""
                INSERT INTO collection_runs (start_time, status)
                VALUES (?, ?)
            """, (datetime.utcnow().isoformat(), 'running'))
            
            self.conn.commit()
            return self.cursor.lastrowid
            
        except Exception as e:
            logger.error(f"Error starting collection run: {e}")
            return -1
    
    def end_collection_run(self, run_id: int, stats: Dict):
        """
        Mark collection run as complete and save stats

        Args:
            run_id: Collection run ID
            stats: Dictionary with collection statistics
        """
        try:
            # Handle both session quota and cumulative quota
            session_quota = stats.get('quota_used', 0)
            cumulative_quota = stats.get('quota_cumulative', session_quota)

            self.cursor.execute("""
                UPDATE collection_runs SET
                    end_time = ?,
                    channels_processed = ?,
                    videos_collected = ?,
                    comments_collected = ?,
                    quota_used = ?,
                    quota_cumulative = ?,
                    status = ?,
                    error_message = ?
                WHERE run_id = ?
            """, (
                datetime.utcnow().isoformat(),
                stats.get('channels_processed', 0),
                stats.get('videos_collected', 0),
                stats.get('comments_collected', 0),
                session_quota,
                cumulative_quota,
                stats.get('status', 'completed'),
                stats.get('error_message'),
                run_id
            ))

            self.conn.commit()
            logger.info(f"Collection run {run_id} completed with quota: {session_quota} (cumulative: {cumulative_quota})")

        except Exception as e:
            logger.error(f"Error ending collection run: {e}")
    
    def get_channel_by_id(self, channel_id: str) -> Optional[Dict]:
        """Get channel data by ID"""
        try:
            self.cursor.execute("""
                SELECT * FROM channels WHERE channel_id = ?
            """, (channel_id,))
            
            row = self.cursor.fetchone()
            if row:
                columns = [desc[0] for desc in self.cursor.description]
                return dict(zip(columns, row))
            return None
            
        except Exception as e:
            logger.error(f"Error getting channel: {e}")
            return None
    
    def get_videos_by_channel(self, channel_id: str, limit: int = 100) -> List[Dict]:
        """Get videos for a channel"""
        try:
            self.cursor.execute("""
                SELECT * FROM videos 
                WHERE channel_id = ?
                ORDER BY published_at DESC
                LIMIT ?
            """, (channel_id, limit))
            
            columns = [desc[0] for desc in self.cursor.description]
            return [dict(zip(columns, row)) for row in self.cursor.fetchall()]
            
        except Exception as e:
            logger.error(f"Error getting videos: {e}")
            return []
    
    def export_to_csv(self, table_name: str, output_path: str) -> bool:
        """
        Export table to CSV
        
        Args:
            table_name: Name of table to export
            output_path: Path for output CSV file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            import csv
            
            self.cursor.execute(f"SELECT * FROM {table_name}")
            rows = self.cursor.fetchall()
            columns = [desc[0] for desc in self.cursor.description]
            
            with open(output_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(columns)
                writer.writerows(rows)
            
            logger.info(f"Exported {len(rows)} rows from {table_name} to {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error exporting to CSV: {e}")
            return False
    
    def track_quota_usage(self, run_id: int, api_method: str, quota_cost: int, details: str = None):
        """
        Track individual API quota usage

        Args:
            run_id: Collection run ID
            api_method: Name of API method called
            quota_cost: Quota units consumed
            details: Optional details about the call
        """
        try:
            self.cursor.execute("""
                INSERT INTO quota_tracking (run_id, timestamp, api_method, quota_cost, details)
                VALUES (?, ?, ?, ?, ?)
            """, (run_id, datetime.utcnow().isoformat(), api_method, quota_cost, details))

            self.conn.commit()

        except Exception as e:
            logger.error(f"Error tracking quota usage: {e}")

    def get_last_quota_cumulative(self) -> int:
        """
        Get the cumulative quota from the most recent collection run

        Returns:
            Cumulative quota used so far, or 0 if no previous runs
        """
        try:
            self.cursor.execute("""
                SELECT quota_cumulative
                FROM collection_runs
                WHERE status IN ('completed', 'running')
                ORDER BY run_id DESC
                LIMIT 1
            """)

            result = self.cursor.fetchone()
            if result and result[0] is not None:
                return result[0]
            return 0

        except Exception as e:
            logger.error(f"Error getting last cumulative quota: {e}")
            return 0

    def update_run_quota(self, run_id: int, session_quota: int, cumulative_quota: int):
        """
        Update quota values for a running collection

        Args:
            run_id: Collection run ID
            session_quota: Quota used in current session
            cumulative_quota: Total cumulative quota
        """
        try:
            self.cursor.execute("""
                UPDATE collection_runs
                SET quota_used = ?, quota_cumulative = ?
                WHERE run_id = ?
            """, (session_quota, cumulative_quota, run_id))

            self.conn.commit()

        except Exception as e:
            logger.error(f"Error updating run quota: {e}")

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")