# YouTube Monitoring Pipeline - Project Instructions

## Project Context

This is a YouTube data collection pipeline for computational social science research. The user is collecting data from European news outlet YouTube channels to study polarization, toxicity, narratives, and trust in online media.

**Project Location:** `/Users/losardo/Documents/Youtube/youtube_monitoring_pipeline`

## What Claude Should Know

### Project Purpose
- Collect comprehensive YouTube data: channels → videos → comments → captions
- Target: ~6,700 European news outlet YouTube channels
- Expected output: 150,000-350,000 videos, 2-6 million comments
- Collection strategy: exhaustive (ALL videos, ALL comments, no sampling)

### Key Files to Reference

| File | When to Reference |
|------|-------------------|
| `CLAUDE.md` | Detailed technical documentation, API costs, architecture |
| `collect.py` | Main collection script - check for command options |
| `view_data.py` | Data inspection - help user query collected data |
| `src/youtube_client.py` | YouTube API wrapper - for API-related questions |
| `src/database.py` | Database schema - for SQL queries or data structure questions |
| `config/config_comprehensive.yaml` | Configuration settings |
| `LOGBOOK.md` | Collection history and current status |
| `data/youtube_monitoring.db` | SQLite database with collected data |

### Common Tasks Claude May Help With

1. **Running collection**: `python collect.py --sources data/sources.csv [options]`
2. **Resuming interrupted collection**: Add `--resume` flag
3. **Viewing statistics**: `python view_data.py --stats`
4. **Writing SQL queries** against the SQLite database
5. **Debugging API issues** - check quota, rate limits, channel URL formats
6. **Analyzing collected data** - the database has tables: `channels`, `videos`, `comments`, `caption_tracks`, `collection_runs`

### Database Schema Summary

```
channels: channel_id, title, subscriber_count, video_count, source_domain, source_rating, source_orientation
videos: video_id, channel_id, title, view_count, like_count, comment_count, published_at
comments: comment_id, video_id, parent_id, text, author_name, like_count, published_at
caption_tracks: track_id, video_id, language, is_auto_generated
```

### API Quota Awareness

- Default: 10,000 units/day | Production: 1,000,000 units/day
- Channel info: 1 unit | Video page: 1 unit | Comment page: 1 unit
- Search fallback (for /c/ and /user/ URLs): 100 units - expensive!
- Quota resets at midnight Pacific Time

### When User Asks About...

- **Collection status**: Check `LOGBOOK.md` or suggest `python view_data.py --stats`
- **Errors during collection**: Check `logs/pipeline.log`
- **Data queries**: Write SQL for `data/youtube_monitoring.db`
- **Resuming work**: Use `--resume` flag with collect.py
- **Testing changes**: Suggest `--max-channels 3` for small test runs

### Important Constraints

1. API key stored in config files - never output or commit these
2. Collection can take days for full dataset - checkpoint system enables resumption
3. Some channels will fail (deleted, private, URL issues) - ~40-60% success rate expected
4. Comments disabled on some videos is normal, not an error

## Response Style

When helping with this project:
- Reference specific files and line numbers when discussing code
- Provide complete, runnable commands
- For data questions, provide SQL queries the user can run
- Be aware this is research data - accuracy and completeness matter
