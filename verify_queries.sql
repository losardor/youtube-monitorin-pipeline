-- YouTube Monitoring Pipeline - Production Verification Queries
-- Run these queries to verify database state and quota tracking

-- ============================================================
-- BASIC DATABASE HEALTH CHECKS
-- ============================================================

-- Check all tables exist and their row counts
SELECT 'channels' as table_name, COUNT(*) as row_count FROM channels
UNION ALL
SELECT 'videos', COUNT(*) FROM videos
UNION ALL
SELECT 'comments', COUNT(*) FROM comments
UNION ALL
SELECT 'caption_tracks', COUNT(*) FROM caption_tracks
UNION ALL
SELECT 'collection_runs', COUNT(*) FROM collection_runs
UNION ALL
SELECT 'quota_tracking', COUNT(*) FROM quota_tracking;

-- ============================================================
-- COLLECTION RUN ANALYSIS
-- ============================================================

-- View recent collection runs with quota information
SELECT
    run_id,
    start_time,
    end_time,
    status,
    channels_processed,
    videos_collected,
    comments_collected,
    quota_used as session_quota,
    quota_cumulative as total_quota,
    ROUND((quota_cumulative / 1000000.0) * 100, 2) || '%' as quota_percent_used
FROM collection_runs
ORDER BY run_id DESC
LIMIT 10;

-- Check for quota continuity across runs (should show consistent progression)
SELECT
    run_id,
    quota_cumulative,
    quota_cumulative - LAG(quota_cumulative) OVER (ORDER BY run_id) as session_quota_calculated,
    quota_used as session_quota_reported,
    CASE
        WHEN quota_cumulative - LAG(quota_cumulative) OVER (ORDER BY run_id) = quota_used
        THEN 'MATCH ✓'
        ELSE 'MISMATCH ✗'
    END as verification
FROM collection_runs
WHERE quota_cumulative IS NOT NULL
ORDER BY run_id DESC
LIMIT 10;

-- ============================================================
-- QUOTA TRACKING ANALYSIS
-- ============================================================

-- Detailed quota breakdown by API method for current/last run
SELECT
    api_method,
    COUNT(*) as api_calls,
    SUM(quota_cost) as total_quota,
    AVG(quota_cost) as avg_quota_per_call
FROM quota_tracking
WHERE run_id = (SELECT MAX(run_id) FROM collection_runs)
GROUP BY api_method
ORDER BY total_quota DESC;

-- Verify quota tracking completeness
SELECT
    cr.run_id,
    cr.quota_used as reported_quota,
    COALESCE(qt.calculated_quota, 0) as calculated_quota,
    CASE
        WHEN ABS(cr.quota_used - COALESCE(qt.calculated_quota, 0)) < 10
        THEN 'ACCURATE ✓'
        ELSE 'DISCREPANCY ✗ (diff: ' || ABS(cr.quota_used - COALESCE(qt.calculated_quota, 0)) || ')'
    END as accuracy
FROM collection_runs cr
LEFT JOIN (
    SELECT run_id, SUM(quota_cost) as calculated_quota
    FROM quota_tracking
    GROUP BY run_id
) qt ON cr.run_id = qt.run_id
WHERE cr.status != 'initialized'
ORDER BY cr.run_id DESC
LIMIT 10;

-- ============================================================
-- CHANNEL COLLECTION STATISTICS
-- ============================================================

-- Channels with most content collected
SELECT
    c.channel_title,
    c.subscriber_count,
    COUNT(DISTINCT v.video_id) as videos_collected,
    COUNT(DISTINCT cm.comment_id) as comments_collected,
    c.collection_date
FROM channels c
LEFT JOIN videos v ON c.channel_id = v.channel_id
LEFT JOIN comments cm ON v.video_id = cm.video_id
GROUP BY c.channel_id
ORDER BY videos_collected DESC
LIMIT 20;

-- Collection success rate analysis
SELECT
    source_domain,
    COUNT(*) as total_channels,
    SUM(CASE WHEN collection_date IS NOT NULL THEN 1 ELSE 0 END) as collected,
    ROUND(
        SUM(CASE WHEN collection_date IS NOT NULL THEN 1 ELSE 0 END) * 100.0 / COUNT(*),
        2
    ) || '%' as success_rate
FROM channels
GROUP BY source_domain
ORDER BY total_channels DESC;

-- ============================================================
-- VIDEO COLLECTION PATTERNS
-- ============================================================

-- Videos with most engagement
SELECT
    v.video_title,
    c.channel_title,
    v.view_count,
    v.like_count,
    v.comment_count,
    v.published_at
FROM videos v
JOIN channels c ON v.channel_id = c.channel_id
WHERE v.view_count IS NOT NULL
ORDER BY v.view_count DESC
LIMIT 20;

-- Comment collection coverage
SELECT
    has_comments.status,
    COUNT(*) as video_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) || '%' as percentage
FROM (
    SELECT
        v.video_id,
        CASE
            WHEN v.comment_count = 0 THEN 'Comments Disabled'
            WHEN EXISTS (SELECT 1 FROM comments WHERE video_id = v.video_id) THEN 'Comments Collected'
            ELSE 'Comments Not Collected'
        END as status
    FROM videos v
) has_comments
GROUP BY has_comments.status;

-- ============================================================
-- CHECKPOINT AND RESUME VERIFICATION
-- ============================================================

-- Check for incomplete runs (potential resume candidates)
SELECT
    run_id,
    start_time,
    status,
    channels_processed,
    quota_cumulative,
    'python collect.py --sources data/sources.csv --resume' as resume_command
FROM collection_runs
WHERE status IN ('running', 'interrupted')
ORDER BY run_id DESC;

-- ============================================================
-- PRODUCTION READINESS CHECKS
-- ============================================================

-- Verify quota_cumulative column exists and is being populated
SELECT
    CASE
        WHEN COUNT(*) > 0 AND SUM(CASE WHEN quota_cumulative IS NOT NULL THEN 1 ELSE 0 END) > 0
        THEN 'READY ✓ - Quota tracking is functional'
        ELSE 'NOT READY ✗ - Quota tracking needs fix'
    END as quota_tracking_status
FROM collection_runs
WHERE run_id = (SELECT MAX(run_id) FROM collection_runs);

-- Check for any data integrity issues
SELECT 'Orphaned videos' as issue, COUNT(*) as count
FROM videos v
WHERE NOT EXISTS (SELECT 1 FROM channels WHERE channel_id = v.channel_id)
UNION ALL
SELECT 'Orphaned comments', COUNT(*)
FROM comments c
WHERE NOT EXISTS (SELECT 1 FROM videos WHERE video_id = c.video_id)
UNION ALL
SELECT 'Duplicate channels', COUNT(*) - COUNT(DISTINCT channel_id)
FROM channels
UNION ALL
SELECT 'Duplicate videos', COUNT(*) - COUNT(DISTINCT video_id)
FROM videos;

-- ============================================================
-- QUOTA PROJECTION
-- ============================================================

-- Estimate quota needs based on current collection patterns
WITH quota_stats AS (
    SELECT
        AVG(quota_used * 1.0 / NULLIF(channels_processed, 0)) as avg_quota_per_channel,
        MAX(quota_cumulative) as current_cumulative
    FROM collection_runs
    WHERE channels_processed > 0 AND quota_used IS NOT NULL
)
SELECT
    ROUND(avg_quota_per_channel, 2) as avg_quota_per_channel,
    current_cumulative as quota_used_so_far,
    1000000 - current_cumulative as quota_remaining,
    ROUND((1000000 - current_cumulative) / NULLIF(avg_quota_per_channel, 0), 0) as estimated_channels_remaining,
    ROUND(current_cumulative * 100.0 / 1000000, 2) || '%' as quota_utilization
FROM quota_stats;

-- ============================================================
-- COLLECTION PERFORMANCE METRICS
-- ============================================================

-- Collection speed analysis (last 5 runs)
SELECT
    run_id,
    channels_processed,
    videos_collected,
    comments_collected,
    ROUND((julianday(end_time) - julianday(start_time)) * 24, 2) as hours_elapsed,
    ROUND(channels_processed / NULLIF((julianday(end_time) - julianday(start_time)) * 24, 0), 2) as channels_per_hour,
    ROUND(videos_collected / NULLIF((julianday(end_time) - julianday(start_time)) * 24, 0), 2) as videos_per_hour
FROM collection_runs
WHERE end_time IS NOT NULL AND channels_processed > 0
ORDER BY run_id DESC
LIMIT 5;