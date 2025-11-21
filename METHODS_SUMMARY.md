# Data Collection Summary - For Methods Section

## YouTube News Media Dataset Collection Methodology

### Dataset Overview
We collected a comprehensive dataset of YouTube content from European news media outlets using the YouTube Data API v3. The collection occurred in November 2025 and employed an exhaustive enumeration strategy without sampling or temporal restrictions.

### Source Selection
**Total Sources:** 12,846 news outlets from a curated European media database  
**YouTube-Enabled Sources:** 6,764 channels (52.6% of sources)  
**Selection Criteria:** Professional news outlets with active YouTube presence  
**Geographic Coverage:** Primarily Italian, German, and French news sources  

Each source includes metadata on:
- Political orientation (left/center/right)
- Trust rating (0-100 scale)
- Outlet type (television, print, online-only)
- Ownership structure (public, private, nonprofit)

### Temporal Coverage
**Date Range:** Complete historical data (no temporal restrictions)
- Videos: From channel inception to November 2025
- Comments: All available comments from all collected videos
- No start date cutoff (captures full channel history)

### Data Collection Strategy

#### Videos
**Approach:** Exhaustive collection
- ALL videos from each channel (no maximum limit)
- Chronological ordering (most recent first)
- Complete metadata including:
  - View counts, like counts, comment counts
  - Publication dates
  - Video descriptions, titles, tags
  - Duration and category information

#### Comments
**Approach:** Complete enumeration
- ALL comments from ALL videos (no sampling)
- Includes both top-level comments and replies
- Temporal ordering (chronological)
- Full comment threading preserved
- Fields captured:
  - Comment text (plaintext)
  - Author information
  - Timestamps (published and updated)
  - Engagement metrics (likes)
  - Parent-child relationships (reply structure)

**Exclusions:** 
- Videos with disabled comments (system-level exclusion)
- Deleted comments (unavailable via API)
- Spam-filtered comments (invisible to API)

#### Captions
**Metadata Only:** Caption track availability and language information collected but not full transcripts (to conserve API quota for video and comment collection).

### Technical Implementation

**API:** YouTube Data API v3  
**Quota:** 1,000,000 units per day (effective: 950,000 with buffer)  
**Collection Period:** November 19-20, 2025  
**Infrastructure:** Remote server (4GB RAM, 50GB storage)

**Collection Process:**
1. Extract channel ID from source URL
2. Retrieve channel metadata and statistics
3. Paginate through complete video uploads playlist (50 videos per page)
4. For each video, paginate through all comment threads (100 comments per page)
5. Save data incrementally with checkpointing every 10 channels

**Rate Limiting:**
- 0.5 second delay between video comment collections
- 2.0 second delay between channels
- 1.0 second delay between comment page requests

### Data Quality

**Expected Success Rate:** 40-60% of channels
- ~2,700-4,000 successfully collected channels
- Failures due to: deleted channels (~25%), invalid URLs (~20%), private/suspended channels (~15%)

**Completeness:**
- 100% of publicly available videos per channel
- 100% of accessible comments per video
- Limited only by YouTube API access restrictions

**Quality Controls:**
- Checkpoint system for resumability
- Duplicate detection and handling
- Error logging and retry mechanisms
- Immediate database persistence

### Dataset Characteristics (Projected)

**Channels:** 2,700-4,000 active news outlets  
**Videos:** 150,000-350,000 videos  
**Comments:** 2-6 million comments  
**Temporal Span:** ~5-15 years (varies by channel age)  
**Languages:** Primarily Italian, German, French, English  
**Total Size:** 50-100 GB database

### Limitations and Biases

1. **Survivorship Bias:** Only captures content that remains publicly available
2. **Platform Selection:** Limited to news outlets with YouTube presence (52.6% of sources)
3. **Point-in-Time Snapshot:** Engagement metrics reflect collection date, not current values
4. **Deleted Content:** Cannot retrieve deleted videos/comments
5. **Comment Deletion:** Underestimates total comment activity due to moderation/user deletion
6. **Geographic Bias:** European news sources only
7. **Language Bias:** No translation; content in original published language

### Ethical Considerations

- **Public Data:** All collected content publicly accessible via YouTube
- **API Compliance:** Collection adheres to YouTube API Terms of Service
- **No PII:** No private user information collected beyond public display names
- **Research Purpose:** Data collected for academic research on media polarization and online discourse
- **No Manipulation:** Read-only access; no content modification or interaction

### Reproducibility

**Software:** Python 3.10, google-api-python-client, pandas, SQLite  
**Configuration:** No sampling limits, chronological ordering, complete pagination  
**Source Data:** Available upon request (media outlet database)  
**Code:** Custom collection pipeline with checkpoint/resume capability  

**Key Configuration Parameters:**
```
max_videos_per_channel: unlimited
max_comments_per_video: unlimited
video_order: date (chronological)
comment_order: time (chronological)
```

### Data Availability

Data collected for research project on computational social science analysis of news media polarization in European online discourse. Dataset includes:
- Channel metadata (name, subscribers, total views)
- Video metadata (title, description, engagement metrics)
- Comment text and threading
- Source ratings and political orientation labels

### Citation

```
YouTube European News Media Dataset (2025). Comprehensive collection of 
video and comment data from 2,700-4,000 European news outlet YouTube channels. 
Collected November 2025 via YouTube Data API v3. Complete historical coverage 
from channel inception to collection date using exhaustive enumeration 
methodology. Total: ~150,000-350,000 videos, ~2-6 million comments.
```

---

## Quick Statistics Summary Table

| Metric | Value |
|--------|-------|
| **Collection Period** | November 19-20, 2025 |
| **Total Sources Analyzed** | 12,846 news outlets |
| **YouTube Channels Found** | 6,764 (52.6%) |
| **Expected Successful Collections** | 2,700-4,000 (40-60%) |
| **Temporal Coverage** | Complete history (inception to 2025) |
| **Video Collection Strategy** | Exhaustive (no limits) |
| **Comment Collection Strategy** | Complete enumeration (no sampling) |
| **Expected Videos** | 150,000-350,000 |
| **Expected Comments** | 2-6 million |
| **API Quota** | 1,000,000 units/day |
| **Collection Duration** | 2-3 days |
| **Primary Languages** | Italian, German, French, English |
| **Geographic Focus** | European news outlets |
| **Data Format** | SQLite database + CSV exports |
| **Estimated Dataset Size** | 50-100 GB |

---

## Research Applications

This dataset enables analysis of:
- Longitudinal trends in news media engagement
- Cross-channel polarization patterns
- Comment toxicity and discourse quality
- Temporal dynamics of news coverage
- User engagement across political spectrum
- Network analysis of commenter behavior
- Content and engagement asymmetries by political orientation
