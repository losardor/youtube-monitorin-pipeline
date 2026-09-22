"""
Database Module for YouTube Monitoring Pipeline
Handles data persistence using SQLite or PostgreSQL
"""

import sqlite3
import logging
from pathlib import Path

from src.timeutil import utcnow
from typing import List, Dict, Optional, Any
from datetime import datetime
import json

logger = logging.getLogger(__name__)


class ReplicaRefused(RuntimeError):
    """The named file is a replica and was opened without acknowledgement."""


def guard_replica(db_path: str, allow_replica: bool = False) -> None:
    """
    Refuse to open a database whose filename marks it a replica.

    After the cluster cutover the authoritative file lives on gdelt-server and
    the workstation copy is renamed *.replica.db. Writing to the replica would
    produce a second divergent history that looks authoritative -- the failure
    mode is silent, so the guard is on the filename rather than on intent.
    """
    if 'replica' in Path(db_path).name.lower() and not allow_replica:
        raise ReplicaRefused(
            f"{db_path} is a replica, not the production database.\n"
            f"Production lives on gdelt-server:/data/ytmon/youtube_monitoring.db "
            f"as of the phase 3 cutover.\n"
            f"Pass --i-know-this-is-a-replica to operate on it anyway."
        )


class Database:
    """Database handler for YouTube monitoring data"""
    
    def __init__(self, db_path: str = "data/youtube_monitoring.db",
                 allow_replica: bool = False):
        """
        Initialize database connection
        
        Args:
            db_path: Path to SQLite database file
        """
        guard_replica(db_path, allow_replica)
        self.db_path = db_path
        self.conn = None
        self.cursor = None
        self._connect()
        self._create_tables()
        
    def _connect(self):
        """Establish database connection"""
        try:
            self.conn = sqlite3.connect(self.db_path)
            # Rows are addressable by column name as well as position.
            # sqlite3.Row is a superset of a tuple -- indexing, unpacking and
            # iteration all still work -- so this is safe for existing callers,
            # and it removes the gap that let a test fixture be more capable
            # than production: harvest_comments read row['video_id'] and passed
            # its tests, then failed on the cluster with plain tuples.
            self.conn.row_factory = sqlite3.Row
            self.cursor = self.conn.cursor()
            # Enable foreign keys
            self.cursor.execute("PRAGMA foreign_keys = ON")
            # WAL lets the daily run read while a backfill writes. Set here
            # rather than in a caller so every process that opens the file
            # gets the same journal mode (it is persistent, but a fresh file
            # created by another entry point would otherwise start in DELETE).
            self.cursor.execute("PRAGMA journal_mode = WAL")
            self.cursor.execute("PRAGMA synchronous = NORMAL")
            self.cursor.execute("PRAGMA busy_timeout = 30000")
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
            
            # --- Longitudinal monitoring tables -------------------------------
            # The YouTube Data API exposes only *current* statistics; there is
            # no history endpoint. Longitudinal signal has to be manufactured by
            # repeated observation, so these tables are append-only: every run
            # adds a row keyed by (id, observed_at) and nothing is overwritten.
            # The latest-observed columns on channels/videos stay as they are so
            # view_data.py and existing SQL keep working.
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS channel_snapshots (
                    channel_id         TEXT NOT NULL,
                    observed_at        TEXT NOT NULL,
                    subscriber_count   INTEGER,
                    hidden_subscribers INTEGER,
                    view_count         INTEGER,
                    video_count        INTEGER,
                    PRIMARY KEY (channel_id, observed_at)
                )
            """)

            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS video_snapshots (
                    video_id      TEXT NOT NULL,
                    observed_at   TEXT NOT NULL,
                    view_count    INTEGER,
                    like_count    INTEGER,
                    comment_count INTEGER,
                    PRIMARY KEY (video_id, observed_at)
                )
            """)

            # day is the Pacific-time billing day, because that is when the
            # API's own quota counter resets.
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS quota_ledger (
                    day         TEXT NOT NULL,
                    endpoint    TEXT NOT NULL,
                    calls       INTEGER,
                    units       INTEGER,
                    error_calls INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (day, endpoint)
                )
            """)

            # error_calls counts responses the API served with a non-quota
            # error. Whether Google bills those is not documented and could not
            # be settled from 2026-09-16, where the console sat *below* the
            # ledger. Counting them separately makes the question answerable
            # from any later day without changing what is charged.
            self._add_missing_columns('quota_ledger', {
                'error_calls': 'INTEGER NOT NULL DEFAULT 0',
            })

            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS run_log (
                    run_id      TEXT NOT NULL,
                    stage       TEXT,
                    started_at  TEXT,
                    finished_at TEXT,
                    calls       INTEGER,
                    units_spent INTEGER,
                    items       INTEGER,
                    note        TEXT
                )
            """)

            # Columns added to pre-existing tables. Guarded so an old database
            # upgrades in place and a new one is a no-op.
            self._add_missing_columns('channels', {
                'tier': 'INTEGER DEFAULT 0',
                'tier_reason': 'TEXT',
                'wd_item': 'TEXT',
                'wd_class': 'TEXT',
                'uploads_playlist': 'TEXT',
                'last_discovered': 'TEXT',
                'status': 'TEXT',
                'last_checked': 'TEXT',
                'alt_of': 'TEXT',
            })
            self._add_missing_columns('videos', {
                'comments_state': 'TEXT',
                'comment_pages_fetched': 'INTEGER DEFAULT 0',
                'comment_cursor': 'TEXT',
                'last_comment_count': 'INTEGER',
                'last_stats_at': 'TEXT',
            })

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

            self.cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_csnap_time
                ON channel_snapshots(observed_at)
            """)

            self.cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_vsnap_time
                ON video_snapshots(observed_at)
            """)

            self.cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_channels_tier
                ON channels(tier, status)
            """)

            self.cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_videos_cstate
                ON videos(comments_state, published_at)
            """)

            self.conn.commit()
            logger.info("Database tables created/verified")
            
        except Exception as e:
            logger.error(f"Error creating tables: {e}")
            raise
    
    def _add_missing_columns(self, table: str, columns: Dict[str, str]) -> List[str]:
        """
        Add columns to an existing table if they are not already present.

        Args:
            table: Table name
            columns: Mapping of column name -> SQL type/default clause

        Returns:
            Names of the columns actually added
        """
        self.cursor.execute(f"PRAGMA table_info({table})")
        existing = {col[1] for col in self.cursor.fetchall()}

        added = []
        for name, decl in columns.items():
            if name not in existing:
                self.cursor.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
                added.append(name)
                logger.info(f"Added column {table}.{name}")
        return added

    def insert_channel_snapshot(self, channel_id: str, observed_at: str,
                                subscriber_count: Optional[int] = None,
                                hidden_subscribers: Optional[int] = None,
                                view_count: Optional[int] = None,
                                video_count: Optional[int] = None,
                                commit: bool = True) -> bool:
        """
        Append one channel observation.

        Uses INSERT OR IGNORE: (channel_id, observed_at) is the primary key, so
        re-observing the same instant is a no-op rather than an overwrite. This
        is what makes the table append-only and the migration idempotent.
        """
        try:
            self.cursor.execute("""
                INSERT OR IGNORE INTO channel_snapshots (
                    channel_id, observed_at, subscriber_count,
                    hidden_subscribers, view_count, video_count
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (channel_id, observed_at, subscriber_count,
                  hidden_subscribers, view_count, video_count))
            if commit:
                self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error inserting channel snapshot for {channel_id}: {e}")
            return False

    def insert_video_snapshot(self, video_id: str, observed_at: str,
                              view_count: Optional[int] = None,
                              like_count: Optional[int] = None,
                              comment_count: Optional[int] = None,
                              commit: bool = True) -> bool:
        """
        Append one video observation. See insert_channel_snapshot for the
        append-only / idempotence rationale.
        """
        try:
            self.cursor.execute("""
                INSERT OR IGNORE INTO video_snapshots (
                    video_id, observed_at, view_count, like_count, comment_count
                ) VALUES (?, ?, ?, ?, ?)
            """, (video_id, observed_at, view_count, like_count, comment_count))
            if commit:
                self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error inserting video snapshot for {video_id}: {e}")
            return False

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

            channel_id = channel_data['id']
            observed_at = utcnow()

            subscriber_count = int(statistics['subscriberCount']) if statistics.get('subscriberCount') else None
            video_count = int(statistics['videoCount']) if statistics.get('videoCount') else None
            view_count = int(statistics['viewCount']) if statistics.get('viewCount') else None
            hidden_subscribers = statistics.get('hiddenSubscriberCount')
            if hidden_subscribers is not None:
                hidden_subscribers = int(bool(hidden_subscribers))

            uploads_playlist = (channel_data.get('contentDetails', {})
                                            .get('relatedPlaylists', {})
                                            .get('uploads'))

            # INSERT OR REPLACE deletes the old row, so any column not named
            # here would be reset to its default. Columns owned by the daily
            # pipeline (tier, wd_*, status, ...) are carried forward explicitly
            # via subselects; a backfill re-insert must not wipe them.
            self.cursor.execute("""
                INSERT OR REPLACE INTO channels (
                    channel_id, channel_url, channel_title, description, custom_url,
                    published_at, country, subscriber_count, video_count, view_count,
                    topic_categories, keywords, branding_keywords,
                    first_collected_at, last_updated_at,
                    source_domain, source_rating, source_orientation,
                    tier, tier_reason, wd_item, wd_class, uploads_playlist,
                    status, last_checked, last_discovered, alt_of
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    COALESCE((SELECT first_collected_at FROM channels WHERE channel_id = ?), ?),
                    ?, ?, ?, ?,
                    COALESCE((SELECT tier FROM channels WHERE channel_id = ?), 0),
                    (SELECT tier_reason FROM channels WHERE channel_id = ?),
                    (SELECT wd_item  FROM channels WHERE channel_id = ?),
                    (SELECT wd_class FROM channels WHERE channel_id = ?),
                    COALESCE(?, (SELECT uploads_playlist FROM channels WHERE channel_id = ?)),
                    (SELECT status       FROM channels WHERE channel_id = ?),
                    (SELECT last_checked    FROM channels WHERE channel_id = ?),
                    (SELECT last_discovered FROM channels WHERE channel_id = ?),
                    (SELECT alt_of          FROM channels WHERE channel_id = ?)
                )
            """, (
                channel_id,
                f"https://www.youtube.com/channel/{channel_id}",
                snippet.get('title'),
                snippet.get('description'),
                snippet.get('customUrl'),
                snippet.get('publishedAt'),
                snippet.get('country'),
                subscriber_count,
                video_count,
                view_count,
                json.dumps(channel_data.get('topicDetails', {}).get('topicCategories', [])),
                branding.get('keywords'),
                json.dumps(branding.get('keywords', '').split() if branding.get('keywords') else []),
                channel_id, observed_at,          # first_collected_at COALESCE
                observed_at,                      # last_updated_at
                source_metadata.get('domain'),
                source_metadata.get('rating'),
                source_metadata.get('orientation'),
                channel_id,                       # tier
                channel_id,                       # tier_reason
                channel_id,                       # wd_item
                channel_id,                       # wd_class
                uploads_playlist, channel_id,     # uploads_playlist COALESCE
                channel_id,                       # status
                channel_id,                       # last_checked
                channel_id,                       # last_discovered
                channel_id,                       # alt_of
            ))

            # Every write to the latest-observed columns also appends an
            # observation, so the series never has a gap the columns don't.
            self.insert_channel_snapshot(
                channel_id, observed_at,
                subscriber_count=subscriber_count,
                hidden_subscribers=hidden_subscribers,
                view_count=view_count,
                video_count=video_count,
                commit=False,
            )

            self.conn.commit()
            logger.debug(f"Inserted/updated channel: {channel_id}")
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
            
            video_id = video_data['id']
            observed_at = utcnow()

            view_count = int(statistics['viewCount']) if statistics.get('viewCount') else None
            like_count = int(statistics['likeCount']) if statistics.get('likeCount') else None
            # commentCount is absent when comments are disabled: that must stay
            # NULL, not 0, or the series records a false zero.
            comment_count = int(statistics['commentCount']) if statistics.get('commentCount') else None

            # As in insert_channel: carry the daily pipeline's columns across
            # the REPLACE, otherwise a backfill re-insert loses comment paging
            # state and the harvester restarts the video from page one.
            self.cursor.execute("""
                INSERT OR REPLACE INTO videos (
                    video_id, channel_id, title, description, published_at,
                    duration, duration_seconds, category_id, default_language,
                    default_audio_language, view_count, like_count, comment_count,
                    tags, topic_categories, made_for_kids, has_captions,
                    thumbnail_url, collected_at,
                    comments_state, comment_pages_fetched, comment_cursor,
                    last_comment_count, last_stats_at
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    (SELECT comments_state FROM videos WHERE video_id = ?),
                    COALESCE((SELECT comment_pages_fetched FROM videos WHERE video_id = ?), 0),
                    (SELECT comment_cursor     FROM videos WHERE video_id = ?),
                    (SELECT last_comment_count FROM videos WHERE video_id = ?),
                    ?
                )
            """, (
                video_id,
                snippet.get('channelId'),
                snippet.get('title'),
                snippet.get('description'),
                snippet.get('publishedAt'),
                content_details.get('duration'),
                duration_seconds,
                snippet.get('categoryId'),
                snippet.get('defaultLanguage'),
                snippet.get('defaultAudioLanguage'),
                view_count,
                like_count,
                comment_count,
                json.dumps(snippet.get('tags', [])),
                json.dumps(video_data.get('topicDetails', {}).get('topicCategories', [])),
                status.get('madeForKids'),
                content_details.get('caption') == 'true',
                snippet.get('thumbnails', {}).get('high', {}).get('url'),
                observed_at,
                video_id,                 # comments_state
                video_id,                 # comment_pages_fetched
                video_id,                 # comment_cursor
                video_id,                 # last_comment_count
                observed_at,              # last_stats_at
            ))

            self.insert_video_snapshot(
                video_id, observed_at,
                view_count=view_count,
                like_count=like_count,
                comment_count=comment_count,
                commit=False,
            )

            self.conn.commit()
            logger.debug(f"Inserted/updated video: {video_id}")
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
                utcnow()
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
                utcnow()
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
            """, (utcnow(), 'running'))
            
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
                utcnow(),
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
            """, (run_id, utcnow(), api_method, quota_cost, details))

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