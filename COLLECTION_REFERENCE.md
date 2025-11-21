# Data Collection Quick Reference Card

## Collection Strategy at a Glance

### What Was Collected

| Data Type | Strategy | Details |
|-----------|----------|---------|
| **Videos** | ALL videos | No limit, complete history |
| **Comments** | ALL comments | No limit, includes replies |
| **Captions** | Metadata only | Languages available, not full text |
| **Channels** | 6,764 queued | Expected 2,700-4,000 successful |
| **Time Period** | Complete history | Channel inception → Nov 2025 |

---

## Key Parameters

### Temporal
- **Start Date:** None (collects from beginning of channel)
- **End Date:** November 2025 (collection date)
- **Historical Depth:** Full channel history (5-15 years typical)

### Volume Limits
- **Max Videos/Channel:** ∞ (unlimited)
- **Max Comments/Video:** ∞ (unlimited)  
- **Max Comment Replies:** ∞ (unlimited)
- **Pagination:** Complete (all pages)

### Ordering
- **Videos:** Chronological by date (newest first)
- **Comments:** Chronological by time (oldest first)
- **Comment Threads:** Preserved parent-child structure

### Filters
- **Language Filter:** None
- **Geographic Filter:** None
- **Engagement Filter:** None
- **Age Filter:** None
- **Content Filter:** None

---

## What Is NOT Collected

❌ **Video/Comment Text Translations** (original language only)  
❌ **Full Caption Transcripts** (only metadata)  
❌ **Deleted/Private Content** (not accessible)  
❌ **Historical Edits** (only current version)  
❌ **User Demographics** (beyond public display names)  
❌ **View/Like History** (only snapshot at collection time)  
❌ **Unlisted Videos** (not in public uploads)  

---

## Collection Guarantees

### ✅ Completeness Guarantees
- **100%** of publicly available videos
- **100%** of accessible comments  
- **100%** of comment replies
- **100%** of caption metadata

### ⚠️ Known Limitations
- Videos deleted before collection: Not captured
- Comments disabled by owner: Not captured
- Comments deleted by users/mods: Not captured
- Spam-filtered comments: Not captured (invisible to API)
- Geographic restrictions: May affect some content

---

## Technical Specifications

### API Details
```
API: YouTube Data API v3
Quota: 1,000,000 units/day (950K effective with buffer)
Rate Limits: 
  - 0.3s between video pages
  - 0.5s between videos
  - 1.0s between comment pages
  - 2.0s between channels
```

### Quota Costs
```
Channel info:        1 unit
Video page (50):     1 unit  
Video details (50):  1 unit
Comment page (100):  1 unit
Caption list:        1 unit

Average per channel: ~140 units
  (varies: 50-500 depending on channel size)
```

### Data Storage
```
Database: SQLite (youtube_monitoring.db)
Tables: channels, videos, comments, caption_tracks, collection_runs
Size: 50-100 GB (estimated final)
Format: Also exportable to CSV
```

---

## Success Rates and Quality

### Expected Outcomes
```
Channels queued:     6,764
Success rate:        40-60%
Successful channels: 2,700-4,000
Failed channels:     2,764-4,064

Videos:             150,000-350,000
Comments:           2-6 million
Unique commenters:  500K-1.5M
```

### Failure Reasons (Typical Distribution)
```
Deleted channels:         25-30%
Invalid/outdated URLs:    20-25%
Private/suspended:        10-15%
Geographic restrictions:  2-5%
API errors:               1-3%
```

---

## Data Freshness and Updates

### Snapshot Characteristics
- **Collection Date:** November 19-20, 2025
- **Metrics Timestamp:** Values at collection time
- **Not Real-Time:** Engagement metrics will drift from current
- **No Updates:** One-time snapshot, not continuously refreshed

### Temporal Accuracy
```
Video metadata:   Accurate as of Nov 2025
Comment text:     Most recent version only
Engagement:       Nov 2025 snapshot
Channel stats:    Nov 2025 snapshot
Deleted content:  Not captured
```

---

## Comparison: Overview vs Comprehensive Strategy

| Aspect | Overview (v1) | Comprehensive (v2) |
|--------|---------------|-------------------|
| Videos/channel | 50 max | ∞ (unlimited) |
| Comments/video | 100 max | ∞ (unlimited) |
| Comment source | First 5 videos only | ALL videos |
| Captions | No | Metadata yes |
| Quota/channel | ~15 units | ~140 units |
| Time/channel | 2 minutes | 30-60 minutes |
| Data completeness | Sample | Complete |
| Use case | Testing, monitoring | Research dataset |

**This Collection Uses:** Comprehensive (v2)

---

## Data Structure

### Channel Record
```
- channel_id (unique identifier)
- channel_title
- subscriber_count
- total_video_count
- total_view_count
- description
- published_at (channel creation date)
- country
- + source metadata (rating, orientation, etc.)
```

### Video Record
```
- video_id (unique identifier)
- channel_id (foreign key)
- title
- description
- published_at
- duration
- view_count (at collection)
- like_count (at collection)
- comment_count (at collection)
- tags
- category_id
```

### Comment Record
```
- comment_id (unique identifier)
- video_id (foreign key)
- parent_id (for replies, null for top-level)
- text (plaintext)
- author (display name)
- author_channel_id
- published_at
- updated_at
- like_count
- reply_count
```

---

## Research Considerations

### Suitable For
✅ Longitudinal analysis  
✅ Cross-channel comparisons  
✅ Discourse analysis  
✅ Engagement patterns  
✅ Network analysis  
✅ Content analysis  
✅ Temporal trends  

### Not Suitable For
❌ Real-time monitoring  
❌ Causal inference (no control group)  
❌ Representative sampling (biased sample)  
❌ Individual user tracking  
❌ Deleted content analysis  
❌ Private/restricted content  

### Statistical Notes
- **Non-random sample** of news outlets
- **Unequal sizes** (channel subscribers: 30 to 1.1M)
- **Survivorship bias** (deleted content missing)
- **Platform-specific** (YouTube behavior only)
- **Engagement varies** (normalize by channel/video age)

---

## File Locations

### On Server
```
/home/user/youtube_monitoring_pipeline/
├── data/
│   ├── sources.csv                      (input: 12,846 sources)
│   ├── youtube_monitoring.db            (output: all collected data)
│   ├── checkpoints/                     (resume points)
│   └── processed/                       (CSV exports)
├── logs/
│   ├── pipeline.log                     (collection log)
│   └── auto_resume_YYYYMMDD.log         (cron logs)
└── collect_comprehensive_fixed.py       (main collector)
```

### After Export
```
exports_YYYYMMDD.tar.gz
├── channels.csv       (channel metadata)
├── videos.csv         (video metadata)
└── comments.csv       (comment text and threading)
```

---

## Quick Commands

### Check Status
```bash
python view_data.py --stats
```

### Resume Collection
```bash
python collect_comprehensive_fixed.py --sources data/sources.csv --resume
```

### Export Data
```bash
./export_data.sh
```

### Monitor Progress
```bash
tail -f logs/pipeline.log
```

---

## Contact Information

**Collection Date:** November 19-20, 2025  
**Researcher:** Ruggiero Lovreglio  
**Institution:** Sony Computer Science Laboratories - Rome  
**Project:** Computational Social Science - Media Polarization Study  
**Data Format:** SQLite + CSV exports  
**Geographic Focus:** European news outlets  

---

## Version

**Collection Version:** 2.0 (Comprehensive Strategy)  
**Last Updated:** November 20, 2025  
**Documentation Version:** 1.0  
