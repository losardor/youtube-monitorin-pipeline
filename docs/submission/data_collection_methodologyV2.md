# Data Collection Methodology

*YouTube Monitoring Pipeline for Computational Social Science Research on European News Media*

---

## 1. Overview

This document describes the procedure used to construct a large-scale corpus of YouTube channel, video, and comment data from European news outlets. The corpus is designed to support research on polarization, toxicity, narrative dynamics, and audience trust in online news media. Collection was performed using the YouTube Data API v3 through a custom Python pipeline that enforces exhaustive, reproducible, and checkpointable extraction of all available videos and comments from each target channel.

The pipeline is open, auditable, and deterministic with respect to the state of the YouTube platform at collection time. Snapshots of engagement metrics (view counts, like counts, comment counts) reflect point-in-time values on the date each channel was processed; they are not longitudinal measurements.

---

## 2. Sampling Frame

### 2.1 Population and Unit of Analysis

The population of interest is YouTube channels operated by, or affiliated with, European news outlets. The primary unit of analysis is the channel; secondary units are the videos published by each channel and the comments posted under each video.

### 2.2 Source List

The sampling frame was constructed from an external registry of European news outlets containing the following fields per outlet:

- `Youtube` — the outlet's YouTube channel URL (required)
- `Domain` — the outlet's primary web domain
- `Brand Name` — human-readable outlet name
- `Rating` — external source-credibility rating (preserved verbatim from the registry)
- `Orientation` — external political-orientation coding (preserved verbatim)

The initial list comprised approximately 6,700 rows, later reduced to **6,358 unique channel URLs** after deduplication and cleanup (see Section 3). All registry metadata fields are carried forward into the channel records in the database, allowing downstream analyses to condition on source credibility and political orientation without re-coding.

Geographic coverage skews toward Italian, German, and French outlets, with smaller contributions from other European languages.

---

## 3. URL Normalization and Resolution

YouTube channel URLs appear in several historically distinct formats, each with different resolution costs and failure modes on the API. A pre-processing stage normalizes these URLs before any API calls are issued.

### 3.1 URL Formats Encountered

| Format | Count (post-cleanup) | Resolution Strategy | Per-URL Quota Cost |
|---|---|---|---|
| `/channel/UC...` (canonical ID) | 4,536 | `channels.list` by `id` | 1 unit |
| `/@handle` | 375 | `channels.list` by `forHandle` | 1 unit |
| `/c/customname` | 829 | `forUsername` → `search.list` fallback | 1 to 101 units |
| `/user/username` (legacy) | 612 | `forUsername` → `search.list` fallback | 1 to 101 units |
| Other / bare names | 6 | `search.list` | ~100 units |
| **Total** | **6,358** | | |

### 3.2 Cleanup Operations

The following deterministic transformations were applied to the raw URL column before validation:

1. **Comma-joined duplicates**: rows containing two URLs separated by commas were split, keeping the first URL (244 rows fixed).
2. **URL-decoding**: percent-encoded characters (e.g., `%C3%A9` → `é`) were decoded (10 rows fixed).
3. **Path stripping**: trailing suffixes (`/videos`, `/featured`, `/about`) and query parameters (e.g., `?app=desktop`) were removed (188 rows fixed initially; an additional 442 normalizations performed in a later pass).
4. **Manual correction**: 69 rows with malformed inputs (bare channel names, video links, playlist links, non-YouTube URLs) were hand-corrected in a separate file and merged back into the sampling frame; 68 resolved successfully, 1 was dropped.

Backups of the raw source list were retained before each mutation to ensure auditability.

### 3.3 Channel ID Resolution

Each cleaned URL is resolved to a canonical YouTube channel ID (prefix `UC`) by the `YouTubeClient.get_channel_info()` method, which attempts the cheapest resolution path first (by `id`, then by `forHandle`, then by `forUsername`) and falls back to `search.list` only when prior methods return no result. Because `search.list` costs 100 quota units compared to 1 unit for direct lookups, **URL format is a major determinant of total quota consumption** and accordingly motivated a staged validation procedure.

### 3.4 Validation Runs

Validation (resolving every URL to a channel ID and recording success/failure) was performed incrementally under a 10,000-unit/day quota ceiling across multiple runs, with resumption based on a persistent `validation_progress.json` state file. A staged strategy was adopted in the final runs: URLs were pre-partitioned into a "cheap" bucket (`/channel/UC...` and `/@handle`, both 1 unit) and a "risky" bucket (`/c/`, `/user/`, bare names, up to 101 units), with the cheap bucket processed first to avoid exhausting daily quota on expensive fallbacks before clearing the bulk of the list.

Observed success rates on validated URLs range from 77% to 96% depending on the URL-format mix of the batch. Failures overwhelmingly correspond to channels that are genuinely deleted, private, suspended, or never existed at the given URL.

---

## 4. Collection Infrastructure

### 4.1 Software

The pipeline is implemented in Python 3 and structured as follows:

```
youtube_monitoring_pipeline/
├── collect.py                       # Main collector (orchestration)
├── view_data.py                     # Data inspection CLI
├── config/
│   └── config_comprehensive.yaml    # Production configuration
├── src/
│   ├── youtube_client.py            # YouTube Data API v3 wrapper
│   ├── database.py                  # SQLite persistence layer
│   └── utils/helpers.py             # I/O and logging utilities
├── data/
│   ├── sources.csv                  # Input channel list
│   ├── youtube_monitoring.db        # SQLite output database
│   ├── checkpoints/                 # Resumption state
│   └── validation/                  # URL-resolution state
└── logs/
    └── pipeline.log                 # Execution logs
```

### 4.2 API Access

Data is collected exclusively through the official YouTube Data API v3. No scraping, browser automation, or reverse-engineered endpoints are used. All requests are authenticated with an API key issued via Google Cloud Console. The daily quota ceiling is either the default 10,000 units or, after an approved increase, 1,000,000 units.

### 4.3 API Endpoints Used

| Endpoint | Purpose | Cost |
|---|---|---|
| `channels.list` | Channel metadata and statistics | 1 unit |
| `playlistItems.list` (uploads playlist) | Enumerate all videos on a channel | 1 unit per page of 50 |
| `videos.list` | Batch video details and engagement metrics | 1 unit per batch of 50 |
| `commentThreads.list` | Top-level comments with nested replies | 1 unit per page of 100 |
| `comments.list` | Additional replies when a thread exceeds its inline reply limit | 1 unit per page |
| `captions.list` | Caption track metadata (not transcript text) | 1 unit |
| `search.list` | Last-resort channel resolution | 100 units |

---

## 5. Collection Strategy

### 5.1 Exhaustiveness

The collection strategy is **exhaustive by design**: for each successfully resolved channel, the pipeline retrieves every video in the channel's uploads playlist, and for every video, every accessible top-level comment and reply. No random sampling, date restriction, or engagement threshold is applied. This design choice trades quota cost for analytical flexibility, enabling downstream studies to re-sample along any dimension without re-contacting the API.

The following configuration keys enforce exhaustiveness:

```yaml
collection:
  max_videos_per_channel: null   # all videos
  max_comments_per_video: null   # all comments and replies
  start_date: null               # no temporal restriction
  end_date: null
```

### 5.2 Processing Order

For each channel, the pipeline executes the following sequence:

1. Resolve the channel ID and fetch channel-level metadata (`channels.list`).
2. Paginate through the uploads playlist to enumerate video IDs.
3. Request video details in batches of 50 (`videos.list`) to obtain titles, descriptions, tags, duration, category, caption availability, and engagement snapshots.
4. For each video, paginate comment threads (`commentThreads.list`), expanding threads that exceed their inline reply limit via `comments.list`.
5. For each video with captions, record available caption track metadata (language, auto-generated flag). **Transcript text is not downloaded** (see Section 9).
6. Persist results to SQLite immediately (idempotent `INSERT OR REPLACE`), so that an interrupted run never produces inconsistent state.
7. Write a checkpoint every *N* channels (default 10) to `data/checkpoints/latest_checkpoint.json`.

### 5.3 Video and Comment Ordering

- Videos: ordered `date` (chronological, oldest to newest within each channel).
- Comments: ordered `time` (chronological, preserving thread structure).

Ordering choices are recorded in the configuration file and do not affect completeness, only the order in which items are traversed.

### 5.4 Rate Limiting

To avoid triggering API throttling and to stay within polite-usage norms, fixed delays are inserted between operations:

- 0.3 s between video-page requests
- 0.5 s between individual videos
- 1.0 s between comment-thread pages
- 2.0 s between channels

These delays are conservative and represent a soft upper bound on throughput rather than a strict limit imposed by the API.

### 5.5 Checkpointing and Resumption

The pipeline is designed to run across multiple days. A JSON checkpoint containing the set of completed channel IDs is written every 10 channels. On restart with the `--resume` flag, already-completed channels are skipped without re-contacting the API, making multi-day collection deterministic and cost-free to restart.

---

## 6. Data Model

All data are stored in a single SQLite database (`data/youtube_monitoring.db`) with foreign-key constraints enforced.

### 6.1 Tables

**`channels`** — one row per successfully resolved channel.
Key fields: `channel_id` (PK), `title`, `description`, `subscriber_count`, `video_count`, `view_count`, `country`, `published_at`, `topics`, `source_domain`, `source_rating`, `source_orientation`.

**`videos`** — one row per video.
Key fields: `video_id` (PK), `channel_id` (FK), `title`, `description`, `tags`, `duration`, `category_id`, `view_count`, `like_count`, `comment_count`, `has_captions`, `caption_languages`, `made_for_kids`, `published_at`.

**`comments`** — one row per comment or reply.
Key fields: `comment_id` (PK), `video_id` (FK), `parent_id` (self-referential FK for replies), `text`, `author_name`, `author_channel_id`, `like_count`, `reply_count`, `published_at`, `updated_at`.

**`caption_tracks`** — one row per available caption track (metadata only).
Key fields: `track_id` (PK), `video_id` (FK), `language`, `is_auto_generated`, `track_type`.

**`collection_runs`** — one row per invocation of `collect.py`, for operational auditability.
Fields include start/end timestamps, quota consumed, channels attempted/succeeded/failed, videos and comments collected, status, and error messages.

### 6.2 Design Properties

- **Idempotency**: all inserts use `INSERT OR REPLACE`. Re-running the pipeline on an already-collected channel updates its record in place without creating duplicates.
- **Indices**: `channel_id`, `video_id`, and `published_at` are indexed for query performance on typical analytical patterns (per-channel time series, per-video comment retrieval).
- **Source enrichment**: registry fields (`source_domain`, `source_rating`, `source_orientation`) are preserved on the `channels` table, so any video- or comment-level query can trivially join source-credibility and political-orientation labels.
- **Timestamps**: stored as ISO 8601 strings in UTC.
- **JSON-typed fields** (tags, topics, keyword lists, caption languages) are serialized as JSON strings in SQLite `TEXT` columns.

---

## 7. Quota Management

### 7.1 Cost Model

Approximate per-channel cost scales roughly as:

```
cost ≈ 1                             # channel metadata
     + ceil(V / 50)                  # video enumeration (playlist pages)
     + ceil(V / 50)                  # video details batches
     + sum over videos of
         ceil(C_v / 100)             # comment thread pages
         + reply-expansion pages
     + (1 per video with captions)   # caption track list
```

where *V* is the number of videos on the channel and *C_v* is the number of comment threads per video. Empirically this ranges from approximately 50 units for small channels to several hundred units for large, comment-heavy channels.

### 7.2 Operational Bounds

Under the 1,000,000-unit/day production quota, the pipeline is provisioned to process on the order of 2,000–7,000 channels per day, yielding an expected final corpus of approximately 150,000–350,000 videos and 2–6 million comments, subject to channel-mix composition.

The pipeline monitors cumulative quota consumption at each call and halts gracefully when remaining quota falls below a configurable buffer (default: 50,000 units), saving a checkpoint so that the next day's run resumes cleanly after the midnight-Pacific quota reset.

---

## 8. Error Handling and Data Quality

### 8.1 Failure Taxonomy

Channel-level failures fall into the following categories, none of which abort a run:

- **Deleted / private / suspended**: the API returns no channel object. Recorded as failure; no partial data retained.
- **Quota exhaustion mid-channel**: the current channel is marked incomplete, checkpoint is saved, run exits.
- **Comments disabled**: expected for some videos; logged as a warning, not an error.
- **Transient network errors**: retried with exponential backoff (up to 5 attempts).

A consecutive-failure counter halts the run if more than *N* (default 5) channels fail in a row, on the assumption that this indicates a systemic problem rather than sparse individual dead links.

### 8.2 Expected Yield

Based on validation runs, approximately 60–90% of channel URLs resolve successfully to a live channel, with the variance driven primarily by URL-format composition (`/channel/UC...` URLs nearly always resolve; `/c/` and `/user/` URLs have higher failure rates reflecting both genuine dead channels and historical custom-URL drift).

### 8.3 Known Data Quality Issues

1. **`search.list` fallback cost**: a small fraction of `/c/` and `/user/` URLs can only be resolved by a 100-unit search query. The staged validation strategy (Section 3.4) mitigates but does not eliminate this cost.
2. **Quota-403 swallowing** *(known bug, flagged for correction)*: an early version of `youtube_client.get_channel_info` catches `quotaExceeded` 403 responses and returns `None`, which the validator records indistinguishably from a genuine "channel not found." Affected entries are re-validated on subsequent days with fresh quota. Entries matching the pattern `cost=0 AND status=failed AND reason="Channel not found"` in the validation state file are candidates for re-validation. A future client revision will raise an explicit `QuotaExceededError` and halt cleanly.
3. **Engagement snapshots**: view, like, and comment counts reflect the moment of collection. Longitudinal analysis of engagement requires multiple collection passes.
4. **Deleted content mid-collection**: videos or comments deleted after the channel is enumerated but before per-item retrieval will be missing from the corpus. This is expected to be rare but non-zero.

---

## 9. Limitations

The following limitations are intrinsic to the YouTube Data API v3 and must be acknowledged in downstream analysis:

1. **No dislike counts.** YouTube removed public dislike counts in late 2021. The API does not expose them retrospectively. Engagement analysis is restricted to views, likes, and comment volume.
2. **No caption transcripts via API.** `captions.list` returns track metadata, but downloading caption text (`captions.download`) requires OAuth2 ownership of the channel, which is infeasible at scale for third-party channels. Where transcript analysis is required, an auxiliary procedure using the `youtube-transcript-api` library (which scrapes the public caption endpoint) may be used in a separate stage, with explicit acknowledgement of its non-API provenance.
3. **No access to deleted content.** Videos and comments removed before the collection date are not recoverable.
4. **Custom URL resolution is lossy.** Some historical `/c/` and `/user/` URLs no longer resolve even though their underlying channels may still exist under a different handle. Such channels will be missed unless the registry is updated.
5. **Temporal snapshot.** This corpus is a snapshot; repeated collection passes are required to build a longitudinal dataset.
6. **API-surface changes.** YouTube periodically modifies the API. Reproducibility is guaranteed only against the API version and schema at collection time.

---

## 10. Ethical and Legal Considerations

- All data is collected from the official public YouTube Data API v3, under the terms of the YouTube API Services Terms of Service and the Google Developer Policies.
- Only publicly posted content is collected. No private videos, private comments, or authenticated-only content is accessed.
- Author identifiers (`author_name`, `author_channel_id`) are stored as returned by the API. For published analyses, aggregation or pseudonymization of commenter identifiers is recommended where individual-level attribution is not essential to the research question.
- The dataset is retained on secured institutional storage and is not redistributed in raw form.

---

## 11. Reproducibility

### 11.1 Inputs Required to Reproduce

1. A YouTube Data API v3 key with sufficient daily quota (10,000 units minimum for small-scale testing; a production increase to 1,000,000 units is recommended for the full corpus).
2. The input `sources.csv` file (or equivalent registry of channel URLs with optional metadata columns).
3. Python 3 with dependencies listed in `requirements.txt`.

### 11.2 Reproduction Procedure

```bash
# 1. Environment setup
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Configuration
#    Place the API key in config/config_comprehensive.yaml
#    under api.youtube_api_key.

# 3. Sanity check (single-channel test)
python test_api_quick.py
python collect.py --sources data/sources.csv --max-channels 3

# 4. Full collection (multi-day, checkpointed)
python collect.py --sources data/sources.csv \
                  --config config/config_comprehensive.yaml

# 5. Resume after interruption or quota exhaustion
python collect.py --sources data/sources.csv --resume

# 6. Inspect results
python view_data.py --stats
```

### 11.3 Provenance and Auditability

- Every invocation of `collect.py` writes a row to the `collection_runs` table with start/end timestamps, quota consumed, and outcome counts.
- `logs/pipeline.log` provides a full execution trace.
- Checkpoint files (`data/checkpoints/latest_checkpoint.json`) and the validation state file (`data/validation/validation_progress.json`) record the set of processed and validated items. Both are versioned before any non-trivial mutation.
- The `sources.csv` file is backed up before each cleanup operation.

### 11.4 Versioning

- **Pipeline version**: recorded in the `collection_runs` table (software version) and in the project git history.
- **API version**: YouTube Data API v3 as of the collection window.
- **Collection window**: *(to be filled: start date — end date)*.
- **Corpus snapshot date**: *(to be filled)*.

---

## 12. Summary Statistics

*The following table should be populated from the live database at write-up time using `python view_data.py --stats`.*

| Metric | Value |
|---|---|
| Channels in sampling frame | 6,358 |
| Channels successfully resolved | *TBD* |
| Channels with data collected | *TBD* |
| Total videos collected | *TBD* |
| Total comments collected | *TBD* |
| Total caption tracks recorded | *TBD* |
| Collection window (start) | *TBD* |
| Collection window (end) | *TBD* |
| Total API quota consumed | *TBD* |

---

*Document version: draft 1 — April 2026.*
