# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

YouTube Monitoring Pipeline for computational social science research analyzing polarization, toxicity, narratives, and trust in online news media. Collects comprehensive channel, video, and comment data from YouTube news outlets using the YouTube Data API v3.

## Core Commands

### Testing API Connection
```bash
# Quick API key validation
python test_api_quick.py

# Simple test with channel lookup
python test_api_simple.py
```

### Running Data Collection

**Main collector (comprehensive, production):**
```bash
# Full collection with all videos and comments
python collect.py --sources data/sources.csv

# Resume from checkpoint after interruption
python collect.py --sources data/sources.csv --resume

# Test with limited channels
python collect.py --sources data/sources.csv --max-channels 5

# Use specific configuration file
python collect.py --sources data/sources.csv --config config/config_comprehensive.yaml
```

### Data Inspection
```bash
# View collection statistics
python view_data.py --stats

# View top channels
python view_data.py --channels --limit 20

# View videos from specific channel
python view_data.py --videos --channel "Channel Name"

# View comments with filters
python view_data.py --comments --video-title "keyword" --limit 50
```

### Environment Setup
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Architecture

### Data Flow
1. **Input**: CSV file with YouTube channel URLs and metadata (domain, rating, orientation)
2. **Collection**: YouTube API queries for channels → videos → comments → captions
3. **Storage**: SQLite database with immediate persistence + optional CSV/JSON export
4. **Output**: Structured database with full relational integrity

### Main Components

**`collect.py`** - Main collector with comprehensive strategy:
- Collects ALL videos from each channel (no limits)
- Collects ALL comments and replies from ALL videos
- Robust error handling and checkpoint-based resumption
- Quota management (1M units/day with 50K buffer)
- Rate limiting between API calls (0.3-2.0s delays)
- Stats tracking: channels attempted/succeeded/failed, videos, comments

**`src/youtube_client.py`** - YouTube API wrapper:
- `get_channel_info()`: Channel metadata and statistics
- `get_channel_videos()`: Paginated video collection from uploads playlist
- `get_video_details()`: Batch video metadata (50 videos/request)
- `get_video_comments()`: Paginated comment threads with replies
- `get_caption_tracks()`: Caption metadata (languages available)
- Handles channel ID resolution from various URL formats (@handle, /c/, /channel/, /user/)
- Built-in retry logic with exponential backoff

**`src/database.py`** - SQLite persistence layer:
- **Tables**: `channels`, `videos`, `comments`, `caption_tracks`, `collection_runs`
- All inserts use INSERT OR REPLACE for idempotency
- Foreign key constraints enforced (channels ← videos ← comments)
- Indexes on channel_id, video_id, published_at for query performance
- Preserves source metadata (domain, rating, orientation)

**`src/utils/helpers.py`** - Utility functions:
- CSV source loading with metadata preservation
- Channel ID extraction from URLs
- Logging setup with file rotation
- JSON serialization for raw API responses

### Database Schema

**channels**: Channel-level aggregates
- Statistics: subscriber_count, video_count, view_count
- Metadata: description, country, published_at, topics
- Source enrichment: source_domain, source_rating, source_orientation

**videos**: Video-level content and engagement
- Content: title, description, tags, duration
- Engagement: view_count, like_count, comment_count (snapshot at collection time)
- Metadata: category_id, has_captions, caption_languages, made_for_kids

**comments**: Comment text and threading
- Structure: parent_id for threaded replies, reply_count
- Content: text (plaintext), author_name, author_channel_id
- Engagement: like_count, published_at, updated_at

**caption_tracks**: Available caption metadata (NOT full transcripts)
- Language, track type, is_auto_generated flag
- Full transcript download requires OAuth2 (not implemented)

**collection_runs**: Execution tracking and diagnostics
- Start/end timestamps, quota usage, statistics
- Status and error messages for debugging

## Configuration

**`config/config.yaml`**: Basic collection (50 videos, 100 comments)
**`config/config_comprehensive.yaml`**: Comprehensive collection (unlimited)

Key settings:
- `api.youtube_api_key`: YouTube Data API v3 key (required)
- `collection.max_videos_per_channel`: Video limit (null = unlimited)
- `collection.max_comments_per_video`: Comment limit (null = unlimited)
- `rate_limiting.daily_quota`: Default 10000, production uses 1000000
- `rate_limiting.quota_buffer`: Safety margin before stopping
- `output.save_to_database`: Enable SQLite storage
- `output.save_to_csv`: Enable CSV exports to data/processed/
- `output.save_raw_json`: Enable raw API response archival

## Collection Strategy

**Comprehensive Strategy** (`collect.py`):
- ALL videos (complete channel history)
- ALL comments and replies (all videos)
- Caption metadata collection
- ~50-500 quota units per channel (varies by channel size)
- 30-60 minutes per large channel
- Checkpoint-based resumption
- Use for research datasets

### Quota Management

YouTube Data API v3 costs:
- Channel info: 1 unit
- Video page (50 videos): 1 unit
- Video details (batch of 50): 1 unit
- Comment page (100 comments): 1 unit
- Caption list: 1 unit

Default quota: 10,000 units/day
Production quota: 1,000,000 units/day (request increase from Google Cloud Console)

Estimated collection capacity with 1M quota:
- ~2,000-7,000 channels (depending on size)
- ~150,000-350,000 videos
- ~2-6 million comments

## Input Data Format

CSV with required column: `Youtube` (channel URL)
Optional metadata columns preserved as-is: `Domain`, `Brand Name`, `Rating`, `Orientation`, etc.

Supported URL formats:
- `https://www.youtube.com/channel/UC...` (direct channel ID)
- `https://www.youtube.com/@username` (handle)
- `https://www.youtube.com/c/customname` (custom URL)
- `https://www.youtube.com/user/username` (legacy user URL)

## Key Features

### Checkpoint-Based Resumption
`collect.py` saves checkpoints every N channels to `data/checkpoints/latest_checkpoint.json`. Use `--resume` flag to continue after interruption without re-processing completed channels.

### Error Handling
- Channel-level errors don't abort collection (logged and skipped)
- Consecutive failure tracking (stops after excessive failures)
- Quota exhaustion detection (graceful shutdown)
- Comments disabled warnings (expected, not fatal)

### Stats Tracking
Real-time statistics in logs:
- `channels_attempted`: Channels actually processed
- `channels_success`: Successfully collected
- `channels_failed`: Failed (deleted, private, API errors)
- `sources_skipped`: Skipped due to quota/errors
- `videos_collected`, `comments_collected`: Totals
- `quota_used`: Current quota consumption

## Known Limitations

1. **Caption transcripts**: API lists caption tracks but downloading actual text requires OAuth2 authentication. Use `youtube-transcript-api` package as workaround for transcript download.

2. **Dislike counts**: Not available via API (YouTube removed public dislikes in 2021).

3. **Deleted content**: Videos/comments deleted before or during collection are not captured.

4. **Channel URL resolution**: Some vanity URLs may fail to resolve. The client attempts multiple resolution methods but success is not guaranteed.

5. **Comments disabled**: Videos with disabled comments will log warnings (expected behavior).

6. **Temporal snapshots**: Engagement metrics (views, likes, comments) are point-in-time snapshots at collection date, not historical data.

## Testing

Before large-scale collection:
```bash
# Test API key
python test_api_quick.py

# Test with 3-5 channels
python collect.py --sources data/sources.csv --max-channels 3

# Verify data
python view_data.py --stats
```

## Development Notes

- All timestamps stored as ISO 8601 strings
- JSON fields (tags, topics, keywords) stored as JSON strings in SQLite
- Foreign keys enforced for data integrity
- Idempotent inserts (INSERT OR REPLACE) allow safe re-running
- Logging to both console and `logs/pipeline.log`
- Rate limiting delays prevent API throttling: 0.3s (video pages), 0.5s (videos), 1.0s (comment pages), 2.0s (channels)

## File Organization

```
youtube_monitoring_pipeline/
├── collect.py                       # Main data collector
├── view_data.py                     # Data inspection CLI
├── test_api_quick.py               # API key validation
├── config/
│   ├── config.yaml                 # Basic collection config
│   └── config_comprehensive.yaml   # Comprehensive config
├── src/
│   ├── youtube_client.py           # API wrapper
│   ├── database.py                 # SQLite persistence
│   └── utils/
│       └── helpers.py              # Utilities
├── data/
│   ├── sources.csv                 # Input channel list
│   ├── youtube_monitoring.db       # SQLite database
│   ├── checkpoints/                # Resumption checkpoints
│   ├── processed/                  # CSV exports
│   └── raw/                        # Raw JSON responses
└── logs/
    └── pipeline.log                # Execution logs
```

## Research Context

Designed for computational social science research on:
- Polarization: Narrative patterns across news outlets
- Toxicity: Comment sentiment analysis
- Trust: Engagement vs source credibility
- Cross-platform dynamics: YouTube presence of news organizations

Dataset characteristics:
- Geographic focus: European news outlets (Italian, German, French)
- ~6,700 channels queued, ~2,700-4,000 expected success
- Complete channel histories (5-15 years typical)
- Snapshot-based (November 2025 collection)
