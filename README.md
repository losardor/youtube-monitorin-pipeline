# YouTube Monitoring Pipeline

A comprehensive Python-based pipeline for monitoring YouTube channels, collecting video content, engagement metrics, and comments. Designed for computational social science research on polarization, toxicity, narratives, and trust in online media.

## Features

- **Channel Monitoring**: Collect detailed channel metadata, statistics, and branding information
- **Video Collection**: Gather video metadata, engagement metrics, and content details
- **Comment Harvesting**: Extract comments and replies with threading information
- **Caption Support**: Identify available caption tracks and languages
- **Flexible Storage**: SQLite database with optional CSV/JSON export
- **Rate Limiting**: Built-in quota management to respect API limits
- **Batch Processing**: Efficient batch collection from multiple sources
- **Rich Metadata**: Preserve source information (news outlet ratings, orientation, etc.)

## Project Structure

```
youtube_monitoring_pipeline/
├── config/
│   └── config.yaml           # Configuration file
├── data/
│   ├── raw/                  # Raw JSON responses (optional)
│   ├── processed/            # CSV exports
│   └── youtube_monitoring.db # SQLite database
├── logs/
│   └── pipeline.log          # Execution logs
├── src/
│   ├── collector.py          # Main orchestrator
│   ├── youtube_client.py     # YouTube API wrapper
│   ├── database.py           # Database operations
│   └── utils/
│       └── helpers.py        # Utility functions
├── tests/                    # Unit tests (optional)
├── requirements.txt          # Python dependencies
└── README.md                 # This file
```

## Installation

### 1. Prerequisites

- Python 3.8 or higher
- YouTube Data API v3 key ([Get one here](https://console.cloud.google.com/apis/credentials))

### 2. Setup

```bash
# Clone or navigate to the project directory
cd youtube_monitoring_pipeline

# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration

Edit `config/config.yaml` and add your YouTube API key:

```yaml
api:
  youtube_api_key: "YOUR_ACTUAL_API_KEY_HERE"
```

You can also adjust:
- Collection limits (videos per channel, comments per video)
- Date ranges for video collection
- Output formats (database, CSV, JSON)
- Rate limiting settings

## Usage

### Basic Usage

Collect data from a list of YouTube channels in a CSV file:

```bash
python src/collector.py --sources path/to/sources.csv
```

### Testing with Limited Channels

Process only the first 5 channels (useful for testing):

```bash
python src/collector.py --sources path/to/sources.csv --max-channels 5
```

### Custom Configuration

Use a different configuration file:

```bash
python src/collector.py --sources sources.csv --config config/custom_config.yaml
```

## Input CSV Format

The pipeline expects a CSV file with at least a `Youtube` column containing YouTube channel URLs. Additional columns (like `Domain`, `Brand Name`, `Rating`, `Orientation`, etc.) are preserved as metadata.

Example:

```csv
Domain,Brand Name,Youtube,Rating,Orientation
example.com,Example News,https://www.youtube.com/c/ExampleNews,T,Center
```

Supported YouTube URL formats:
- `https://www.youtube.com/channel/UC...`
- `https://www.youtube.com/@username`
- `https://www.youtube.com/c/customname`
- `https://www.youtube.com/user/username`

## Output

### Database Schema

**channels**: Channel-level information
- Channel ID, title, description, URL
- Subscriber count, video count, view count
- Topics, keywords
- Source metadata (domain, rating, orientation, etc.)

**videos**: Video-level information
- Video ID, title, description
- Publication date, duration
- View count, like count, comment count
- Tags, topics, categories
- Caption availability

**comments**: Comment-level information
- Comment ID, text, author
- Like count, reply count
- Publication/update timestamps
- Parent comment (for threading)

**caption_tracks**: Available caption metadata
- Language, track type
- Auto-generated flag

**collection_runs**: Pipeline execution tracking
- Start/end time, status
- Statistics (channels, videos, comments)
- Quota usage

### CSV Exports

When enabled, data is exported to `data/processed/`:
- `channels.csv`
- `videos.csv`
- `comments.csv`
- `caption_tracks.csv`

### Raw JSON

Optional raw API responses saved to `data/raw/` for debugging or archival.

## API Quota Management

YouTube Data API v3 has a default quota of **10,000 units per day**. Different operations cost different amounts:

- Video details: 1 unit
- Comment threads: 1 unit per page
- Search: 100 units
- Captions list: 50 units

The pipeline tracks quota usage and can stop before hitting limits. Configure in `config.yaml`:

```yaml
rate_limiting:
  enabled: true
  daily_quota: 10000
  quota_buffer: 1000  # Stop when 1000 units remain
```

## Research Applications

This pipeline is designed for analyzing:

1. **Polarization**: Track narrative patterns across different news sources
2. **Toxicity**: Analyze comment sentiment and language patterns
3. **Narratives**: Study topic evolution and framing
4. **Trust**: Correlate engagement metrics with source credibility
5. **Cross-platform dynamics**: Compare YouTube presence across different outlets

## Example Analysis Queries

### Most engaging videos by channel
```sql
SELECT channel_id, title, view_count, like_count, comment_count,
       (like_count + comment_count) * 1.0 / view_count as engagement_rate
FROM videos
WHERE view_count > 0
ORDER BY engagement_rate DESC
LIMIT 10;
```

### Comment activity by source orientation
```sql
SELECT c.source_orientation, 
       COUNT(DISTINCT v.video_id) as video_count,
       COUNT(co.comment_id) as total_comments,
       AVG(co.like_count) as avg_comment_likes
FROM channels c
JOIN videos v ON c.channel_id = v.channel_id
JOIN comments co ON v.video_id = co.video_id
GROUP BY c.source_orientation;
```

### Top commenters across videos
```sql
SELECT author_name, author_channel_id,
       COUNT(*) as comment_count,
       SUM(like_count) as total_likes
FROM comments
WHERE parent_id IS NULL  -- Top-level comments only
GROUP BY author_channel_id
ORDER BY comment_count DESC
LIMIT 20;
```

## Limitations

1. **Caption Content**: The API can list caption tracks but downloading actual transcripts requires OAuth2 authentication (not just API key). Consider using `youtube-transcript-api` package as a workaround.

2. **Dislike Counts**: YouTube removed public dislike counts in late 2021 - they're not available via the API.

3. **Recommendation Data**: The API doesn't provide information about why videos are recommended.

4. **Rate Limits**: With default quota (10,000 units/day), you can collect approximately:
   - ~100 channels with 50 videos each and comments
   - Request a quota increase from Google for larger projects

5. **Deleted Content**: Videos/comments deleted after collection won't appear in subsequent runs.

## Requesting Quota Increases

For large-scale research:

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Navigate to APIs & Services > Quotas
3. Request increase for YouTube Data API v3
4. Provide justification (research purpose, expected usage)

Increases to 1,000,000+ units/day are common for academic research.

## Troubleshooting

### "Comments disabled" warnings
Some videos have comments disabled - this is normal and logged as a warning.

### "Could not find channel" errors
Some YouTube URLs may use vanity URLs that require resolution. The pipeline attempts multiple resolution methods.

### Quota exceeded
If you hit quota limits:
- Wait until the quota resets (midnight Pacific Time)
- Request a quota increase
- Adjust `max_videos_per_channel` and `max_comments_per_video` in config

### SSL/Connection errors
Network issues can cause intermittent failures. The pipeline has built-in retry logic (configurable via `max_retries`).

## Development

### Running Tests
```bash
pytest tests/
```

### Adding New Features
1. Create new modules in `src/`
2. Update configuration schema in `config/config.yaml`
3. Add tests in `tests/`

## License

[Specify your license]

## Citation

If you use this pipeline in your research, please cite:

[Your citation information]

## Contact

[Your contact information]

## Acknowledgments

Built for computational social science research on online polarization and trust in news media.
