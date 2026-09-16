"""
Daily monitoring stages.

Four stages, run in order, each with a fixed share of the day's remaining
budget:

  resolve_channels  channels.list, refresh metadata and take a snapshot
  discover_uploads  playlistItems.list on channels.uploads_playlist
  refresh_videos    videos.list, statistics snapshot for tracked videos
  harvest_comments  commentThreads.list, resumable per video

Named `daily`, not `monitor`: monitor_collection.py is the terminal progress
viewer for backfills and the two must not be confused.

Two properties are load-bearing and are what the tests pin down:

  - Every stage stops cleanly when its budget share is spent, leaving enough
    state behind to resume exactly where it stopped on the next run.
  - Snapshots are append-only. Re-observing a channel or video adds a row; it
    never overwrites one. Re-observing a comment inserts nothing and does not
    count towards the run's item total.

Two deliberate differences from the ytmon reference implementation:

  - Tier-aware ordering. Every stage processes tier 0 before tier 1 before
    tier 2, with one shared budget over the union, so lower tiers get only
    what is left after the primary frame is served.
  - Tier-specific depth. max_comment_pages_per_video and comment_tracking_days
    are per-tier mappings, not scalars.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from src.errors import QuotaExhausted, CommentsDisabled, ItemUnavailable, APIError
from src.quota import Budget

logger = logging.getLogger(__name__)

TIERS = (0, 1, 2)

# Tier 3 is "recorded, never collected": the row exists to document that the
# candidate was considered and rejected. No stage may spend a unit on it.
TIER_NEVER_COLLECT = 3


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def utcnow() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def _int(v) -> Optional[int]:
    """Coerce an API statistic to int, preserving absence as None.

    A missing commentCount means comments are disabled, which is not zero.
    """
    if v is None or v == '':
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _iso_days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).replace(tzinfo=None).isoformat()


def _jdump(value) -> Optional[str]:
    return json.dumps(value) if value is not None else None


def _per_tier(cfg_value, tier: int, default):
    """
    Read a possibly per-tier config value.

    Accepts a scalar (same for every tier) or a mapping {tier: value}. YAML
    gives integer keys, JSON and env overrides give strings, so both are tried.
    """
    if cfg_value is None:
        return default
    if isinstance(cfg_value, dict):
        if tier in cfg_value:
            return cfg_value[tier]
        if str(tier) in cfg_value:
            return cfg_value[str(tier)]
        return default
    return cfg_value


def log_run(con, run_id: str, stage: str, started_at: str, budget: Budget,
            items: int, note: str = None) -> None:
    """
    Record one stage in run_log.

    budget.calls is this stage's call count, not the session's: ytmon passed
    gov.session_calls here, which is cumulative and overstates every stage
    after the first.
    """
    con.execute(
        "INSERT INTO run_log (run_id, stage, started_at, finished_at, calls, "
        "units_spent, items, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (run_id, stage, started_at, utcnow(), budget.calls, budget.used, items, note),
    )
    con.commit()


def insert_ignore(con, table: str, rows: List[Dict]) -> int:
    """
    Insert rows, skipping ones already present.

    Returns the number of rows actually inserted, which is what a stage
    reports as items: a comment seen again on a later run is not a new item
    and must not inflate the count.
    """
    if not rows:
        return 0
    cols = list(rows[0].keys())
    sql = (f"INSERT OR IGNORE INTO {table} ({','.join(cols)}) "
           f"VALUES ({','.join('?' * len(cols))})")
    before = con.total_changes
    con.executemany(sql, [tuple(r.get(c) for c in cols) for r in rows])
    con.commit()
    return con.total_changes - before


def _tier_ordered(con, sql: str, params: tuple = ()) -> List[sqlite3.Row]:
    """
    Run a query that selects channels, ordering tier 0 first.

    The caller's SQL supplies its own tail ordering; `{tier_order}` in the SQL
    is replaced by the tier clause so a stage can order within a tier however
    it likes.
    """
    return con.execute(sql.format(tier_order="COALESCE(tier, 0) ASC"), params).fetchall()


# ---------------------------------------------------------------------------
# stage 1: resolve / refresh channels
# ---------------------------------------------------------------------------

def resolve_channels(con, client, cfg: dict, run_id: str) -> dict:
    """
    Refresh channel metadata and append a channel snapshot.

    Also populates uploads_playlist, which stage 2 needs and which costs
    nothing extra: it arrives in contentDetails on the same call.
    """
    started = utcnow()
    budget = Budget(client.governor, cfg['quota']['share_channels'], floor=1)
    stale_before = _iso_days_ago(cfg['schedule']['channel_refresh_days'])

    # max_tier lets a run serve only the primary frame, which is how the first
    # pass after tiering is scoped: resolving tier 1 and 2 as well would spend
    # units the caller did not ask for.
    max_tier = cfg.get('limits', {}).get('max_tier')
    tier_cap = TIER_NEVER_COLLECT - 1 if max_tier is None else int(max_tier)

    rows = _tier_ordered(con, """
        SELECT channel_id FROM channels
         WHERE COALESCE(tier, 0) <= ?
           AND (status IS NULL OR status = 'unresolved'
                OR last_checked IS NULL OR last_checked < ?)
         ORDER BY {tier_order},
                  (last_checked IS NULL) DESC, last_checked ASC
    """, (tier_cap, stale_before))
    todo = [r[0] for r in rows]

    now = utcnow()
    resolved, unresolved = 0, 0

    for batch in _chunks(todo, 50):
        if not budget.ok():
            break
        try:
            page = client.channels_by_id(batch)
        except QuotaExhausted:
            break
        except (ItemUnavailable, APIError) as e:
            logger.warning(f"channels.list batch failed: {e}")
            continue

        returned = set()
        for item in page.get('items', []):
            cid = item['id']
            returned.add(cid)
            sn = item.get('snippet', {})
            st = item.get('statistics', {})
            uploads = (item.get('contentDetails', {})
                           .get('relatedPlaylists', {})
                           .get('uploads'))

            con.execute("""
                UPDATE channels
                   SET channel_title = ?, custom_url = ?, country = ?,
                       published_at = ?, description = ?, topic_categories = ?,
                       uploads_playlist = COALESCE(?, uploads_playlist),
                       subscriber_count = ?, video_count = ?, view_count = ?,
                       status = 'active', last_checked = ?, last_updated_at = ?,
                       first_collected_at = COALESCE(first_collected_at, ?)
                 WHERE channel_id = ?
            """, (
                sn.get('title'), sn.get('customUrl'), sn.get('country'),
                sn.get('publishedAt'), (sn.get('description') or '')[:5000],
                _jdump(item.get('topicDetails', {}).get('topicCategories')),
                uploads,
                _int(st.get('subscriberCount')), _int(st.get('videoCount')),
                _int(st.get('viewCount')),
                now, now, now, cid,
            ))

            con.execute("""
                INSERT OR IGNORE INTO channel_snapshots (
                    channel_id, observed_at, subscriber_count,
                    hidden_subscribers, view_count, video_count
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                cid, now,
                _int(st.get('subscriberCount')),
                int(bool(st.get('hiddenSubscriberCount'))),
                _int(st.get('viewCount')), _int(st.get('videoCount')),
            ))
            resolved += 1

        # Ids the API did not return are dead: terminated, deleted, or wrong.
        # Marked, never deleted -- a channel that 404s today may be a
        # temporary suspension, and the row carries the seed provenance.
        for cid in set(batch) - returned:
            con.execute(
                "UPDATE channels SET status = 'unresolved', last_checked = ? "
                "WHERE channel_id = ?", (now, cid))
            unresolved += 1
        con.commit()

    log_run(con, run_id, 'resolve_channels', started, budget, resolved,
            f"{len(todo)} queued, {unresolved} unresolved")
    return {'queued': len(todo), 'resolved': resolved,
            'unresolved': unresolved, 'units': budget.used,
            'calls': budget.calls}


# ---------------------------------------------------------------------------
# stage 2: discover new uploads
# ---------------------------------------------------------------------------

def discover_uploads(con, client, cfg: dict, run_id: str) -> dict:
    """
    Find new uploads through each channel's uploads playlist.

    playlistItems.list costs 1 unit per page of 50, where search.list would
    cost 100 for the same answer. This is why search is banned on this path.
    """
    started = utcnow()
    budget = Budget(client.governor, cfg['quota']['share_discovery'], floor=1)
    lookback = _iso_days_ago(cfg['schedule']['upload_lookback_days'])
    max_pages = cfg['limits']['max_upload_pages_per_channel']
    stop_known = cfg['limits']['stop_after_known_videos']

    max_tier = cfg.get('limits', {}).get('max_tier')
    tier_cap = TIER_NEVER_COLLECT - 1 if max_tier is None else int(max_tier)

    chans = _tier_ordered(con, """
        SELECT channel_id, uploads_playlist, COALESCE(tier, 0) AS tier
          FROM channels
         WHERE status = 'active' AND uploads_playlist IS NOT NULL
           AND COALESCE(tier, 0) <= ?
         ORDER BY {tier_order}, COALESCE(last_checked, '') ASC
    """, (tier_cap,))

    known = {r[0] for r in con.execute("SELECT video_id FROM videos")}
    now = utcnow()
    new_rows, scanned = [], 0

    for ch in chans:
        if not budget.ok():
            break
        channel_id, playlist = ch[0], ch[1]
        consecutive_known, pages, token = 0, 0, None

        while budget.ok() and pages < max_pages:
            try:
                page = client.playlist_items(playlist, page_token=token)
            except ItemUnavailable:
                con.execute(
                    "UPDATE channels SET status = 'unresolved', last_checked = ? "
                    "WHERE channel_id = ?", (now, channel_id))
                con.commit()
                break
            except QuotaExhausted:
                break
            except APIError as e:
                logger.warning(f"playlistItems failed for {channel_id}: {e}")
                break

            pages += 1
            stop = False
            for item in page.get('items', []):
                cd = item.get('contentDetails', {})
                vid, pub = cd.get('videoId'), cd.get('videoPublishedAt')
                if not vid:
                    continue
                if pub and pub < lookback:
                    # The playlist is newest-first, so everything past here is
                    # older than the lookback window.
                    stop = True
                    continue
                if vid in known:
                    consecutive_known += 1
                    if consecutive_known >= stop_known:
                        stop = True
                    continue
                consecutive_known = 0
                known.add(vid)
                new_rows.append(dict(
                    video_id=vid, channel_id=channel_id, published_at=pub,
                    comments_state='pending', comment_pages_fetched=0,
                    collected_at=now,
                ))

            token = page.get('nextPageToken')
            if stop or not token:
                break
        scanned += 1

    inserted = insert_ignore(con, 'videos', new_rows)
    log_run(con, run_id, 'discover_uploads', started, budget, inserted,
            f"{scanned}/{len(chans)} channels scanned")
    return {'channels_scanned': scanned, 'channels_queued': len(chans),
            'new_videos': inserted, 'units': budget.used, 'calls': budget.calls}


# ---------------------------------------------------------------------------
# stage 3: video metadata and statistics
# ---------------------------------------------------------------------------

def refresh_videos(con, client, cfg: dict, run_id: str) -> dict:
    """Fill in metadata for newly discovered videos and snapshot statistics."""
    started = utcnow()
    budget = Budget(client.governor, cfg['quota']['share_videos'], floor=1)
    stale_before = _iso_days_ago(cfg['schedule']['video_restat_days'])
    track_after = _iso_days_ago(cfg['schedule']['video_tracking_days'])

    rows = con.execute("""
        SELECT v.video_id
          FROM videos v
          LEFT JOIN channels c ON c.channel_id = v.channel_id
         WHERE v.last_stats_at IS NULL
            OR (v.published_at >= ? AND v.last_stats_at < ?)
         ORDER BY COALESCE(c.tier, 0) ASC,
                  (v.last_stats_at IS NULL) DESC, v.published_at DESC
    """, (track_after, stale_before)).fetchall()
    todo = [r[0] for r in rows]

    now = utcnow()
    got, gone = 0, 0

    for batch in _chunks(todo, 50):
        if not budget.ok():
            break
        try:
            page = client.videos_by_id(batch)
        except QuotaExhausted:
            break
        except (ItemUnavailable, APIError) as e:
            logger.warning(f"videos.list batch failed: {e}")
            continue

        returned = set()
        for item in page.get('items', []):
            vid = item['id']
            returned.add(vid)
            sn = item.get('snippet', {})
            st = item.get('statistics', {})
            cd = item.get('contentDetails', {})

            duration_seconds = None
            if cd.get('duration'):
                try:
                    import isodate
                    duration_seconds = int(isodate.parse_duration(cd['duration']).total_seconds())
                except Exception:
                    pass

            view_count = _int(st.get('viewCount'))
            like_count = _int(st.get('likeCount'))
            comment_count = _int(st.get('commentCount'))

            con.execute("""
                UPDATE videos
                   SET channel_id = COALESCE(?, channel_id),
                       title = ?, description = ?, published_at = ?,
                       duration = ?, duration_seconds = ?, category_id = ?,
                       default_language = ?, default_audio_language = ?,
                       tags = ?, topic_categories = ?,
                       made_for_kids = ?, has_captions = ?,
                       thumbnail_url = ?,
                       view_count = ?, like_count = ?, comment_count = ?,
                       last_stats_at = ?, collected_at = COALESCE(collected_at, ?)
                 WHERE video_id = ?
            """, (
                sn.get('channelId'), sn.get('title'), sn.get('description'),
                sn.get('publishedAt'), cd.get('duration'), duration_seconds,
                sn.get('categoryId'), sn.get('defaultLanguage'),
                sn.get('defaultAudioLanguage'),
                _jdump(sn.get('tags')),
                _jdump(item.get('topicDetails', {}).get('topicCategories')),
                item.get('status', {}).get('madeForKids'),
                cd.get('caption') == 'true',
                sn.get('thumbnails', {}).get('high', {}).get('url'),
                view_count, like_count, comment_count,
                now, now, vid,
            ))

            con.execute("""
                INSERT OR IGNORE INTO video_snapshots (
                    video_id, observed_at, view_count, like_count, comment_count
                ) VALUES (?, ?, ?, ?, ?)
            """, (vid, now, view_count, like_count, comment_count))
            got += 1

        for vid in set(batch) - returned:
            con.execute(
                "UPDATE videos SET comments_state = 'unavailable', last_stats_at = ? "
                "WHERE video_id = ?", (now, vid))
            gone += 1
        con.commit()

    log_run(con, run_id, 'refresh_videos', started, budget, got,
            f"{len(todo)} queued, {gone} unavailable")
    return {'queued': len(todo), 'refreshed': got, 'unavailable': gone,
            'units': budget.used, 'calls': budget.calls}


# ---------------------------------------------------------------------------
# stage 4: comments
# ---------------------------------------------------------------------------

def _comment_queue(con, cfg) -> List[sqlite3.Row]:
    """
    Videos worth spending comment quota on, most deserving first.

    Two claims on the budget: videos never pulled, and videos whose comment
    count has grown materially since the last pull, meaning the conversation
    is still live. Growth is measured against the newest statistics snapshot.

    The tracking window is per tier, so a tier-2 video stops being re-polled
    after 7 days while a tier-0 video keeps going for 30.
    """
    growth = cfg['limits']['recomment_growth_ratio']
    tracking = cfg['schedule']['comment_tracking_days']

    clauses, params = [], []
    for tier in TIERS:
        days = _per_tier(tracking, tier, 7)
        clauses.append("(COALESCE(c.tier, 0) = ? AND v.published_at >= ?)")
        params.extend([tier, _iso_days_ago(days)])
    tracking_window = " OR ".join(clauses)

    sql = f"""
        WITH latest AS (
            SELECT video_id, comment_count,
                   ROW_NUMBER() OVER (PARTITION BY video_id
                                      ORDER BY observed_at DESC) AS rn
              FROM video_snapshots
        )
        SELECT v.video_id, v.channel_id, v.comments_state,
               v.comment_pages_fetched, v.comment_cursor, v.last_comment_count,
               l.comment_count AS current_count, v.published_at,
               COALESCE(c.tier, 0) AS tier
          FROM videos v
          LEFT JOIN channels c ON c.channel_id = v.channel_id
          LEFT JOIN latest l ON l.video_id = v.video_id AND l.rn = 1
         WHERE v.comments_state = 'pending'
            OR (v.comments_state = 'done'
                AND ({tracking_window})
                AND l.comment_count IS NOT NULL
                AND l.comment_count > COALESCE(v.last_comment_count, 0) * ?)
         ORDER BY COALESCE(c.tier, 0) ASC,
                  (v.comments_state = 'pending') DESC,
                  v.published_at DESC
    """
    params.append(growth)
    return con.execute(sql, params).fetchall()


def _flatten_thread(item, video_id, channel_id) -> List[Dict]:
    """
    Map one commentThreads item to our comments schema.

    Our table stores the display name directly (author_name) and the plain
    text (text); there is no salted-hash column, and 693k existing rows
    already carry names, so the ytmon privacy indirection is not ported.
    """
    rows = []
    now = utcnow()
    top = item['snippet']['topLevelComment']
    replies = item.get('replies', {}).get('comments', [])

    for comment, parent in [(top, None)] + [(rc, top['id']) for rc in replies]:
        s = comment['snippet']
        rows.append(dict(
            comment_id=comment['id'],
            video_id=video_id,
            parent_id=parent,
            author_name=s.get('authorDisplayName'),
            author_channel_id=(s.get('authorChannelId') or {}).get('value'),
            text=s.get('textOriginal') or s.get('textDisplay'),
            like_count=_int(s.get('likeCount')),
            reply_count=_int(item['snippet'].get('totalReplyCount')) if parent is None else 0,
            published_at=s.get('publishedAt'),
            updated_at=s.get('updatedAt'),
            collected_at=now,
        ))
    return rows


def _fetch_replies(client, budget, parent_id, video_id, channel_id, cfg) -> List[Dict]:
    """Pull replies beyond the handful commentThreads returns inline."""
    out, token, pages = [], None, 0
    cap = cfg['limits']['max_reply_pages_per_comment']
    now = utcnow()

    while budget.ok() and pages < cap:
        try:
            page = client.comment_replies(parent_id, page_token=token)
        except (CommentsDisabled, ItemUnavailable, QuotaExhausted, APIError):
            break
        pages += 1
        for c in page.get('items', []):
            s = c['snippet']
            out.append(dict(
                comment_id=c['id'], video_id=video_id, parent_id=parent_id,
                author_name=s.get('authorDisplayName'),
                author_channel_id=(s.get('authorChannelId') or {}).get('value'),
                text=s.get('textOriginal') or s.get('textDisplay'),
                like_count=_int(s.get('likeCount')), reply_count=0,
                published_at=s.get('publishedAt'), updated_at=s.get('updatedAt'),
                collected_at=now,
            ))
        token = page.get('nextPageToken')
        if not token:
            break
    return out


def harvest_comments(con, client, cfg: dict, run_id: str) -> dict:
    """
    Pull comment threads, resuming mid-video where a previous run stopped.

    The page cap is per tier: tier 0 gets 50 pages (5,000 comments), tier 2
    gets 3. A video that hits its cap is marked done with its cursor kept, so
    it is a deliberate sample rather than an unfinished job.
    """
    started = utcnow()
    budget = Budget(client.governor, cfg['quota']['share_comments'], floor=1)
    order = cfg['limits']['comment_order']
    fetch_replies = bool(cfg['limits']['fetch_full_replies'])
    page_caps = cfg['limits']['max_comment_pages_per_video']

    queue = _comment_queue(con, cfg)
    n_comments, n_videos = 0, 0

    for row in queue:
        if not budget.ok():
            break
        vid = row['video_id']
        tier = row['tier']
        max_pages = _per_tier(page_caps, tier, 3)

        # Resume mid-video if a previous run stopped on budget.
        token = row['comment_cursor']
        pages_done = row['comment_pages_fetched'] or 0
        if row['comments_state'] == 'done':
            # Re-poll from the top: new comments arrive at the front.
            token, pages_done = None, 0

        pages_this_video = 0
        state = 'done'

        try:
            while budget.ok() and pages_this_video < max_pages:
                page = client.comment_threads(vid, page_token=token, order=order)
                pages_this_video += 1
                pages_done += 1

                rows = []
                for item in page.get('items', []):
                    rows += _flatten_thread(item, vid, row['channel_id'])
                    if fetch_replies:
                        total = item['snippet'].get('totalReplyCount') or 0
                        inline = len(item.get('replies', {}).get('comments', []))
                        if total > inline and budget.ok():
                            rows += _fetch_replies(
                                client, budget,
                                item['snippet']['topLevelComment']['id'],
                                vid, row['channel_id'], cfg)

                # Counts new rows only: a comment seen again is not an item.
                n_comments += insert_ignore(con, 'comments', rows)

                token = page.get('nextPageToken')
                if not token:
                    break

            if token and pages_this_video >= max_pages:
                state = 'done'      # page cap reached: a sample, cursor kept
            elif token:
                state = 'pending'   # budget ran out mid-video: resume here
        except CommentsDisabled:
            state, token = 'disabled', None
        except ItemUnavailable:
            state, token = 'unavailable', None
        except QuotaExhausted:
            state = 'pending'
        except APIError as e:
            logger.warning(f"commentThreads failed for {vid}: {e}")
            state = 'pending'

        con.execute("""
            UPDATE videos
               SET comments_state = ?, comment_cursor = ?,
                   comment_pages_fetched = ?,
                   last_comment_count = COALESCE(?, last_comment_count)
             WHERE video_id = ?
        """, (state, token, pages_done, row['current_count'], vid))
        con.commit()
        n_videos += 1

    log_run(con, run_id, 'harvest_comments', started, budget, n_comments,
            f"{n_videos}/{len(queue)} videos")
    return {'queued': len(queue), 'videos_done': n_videos,
            'comments': n_comments, 'units': budget.used, 'calls': budget.calls}


# ---------------------------------------------------------------------------
# orchestration
# ---------------------------------------------------------------------------

STAGES = {
    'channels': resolve_channels,
    'discovery': discover_uploads,
    'videos': refresh_videos,
    'comments': harvest_comments,
}

DEFAULT_STAGES = ('channels', 'discovery', 'videos', 'comments')


def run(con, client, cfg: dict, stages=DEFAULT_STAGES) -> dict:
    """Run the stages in order and return a report dict (one JSON log line)."""
    run_id = uuid.uuid4().hex[:12]
    report = {
        'run_id': run_id,
        'started_at': utcnow(),
        'quota_before': client.governor.spent_today(),
        'stages': {},
    }

    for name in stages:
        if name not in STAGES:
            raise ValueError(f"unknown stage {name!r}; "
                             f"expected one of {', '.join(STAGES)}")
        logger.info(f"stage {name} starting")
        report['stages'][name] = STAGES[name](con, client, cfg, run_id)
        logger.info(f"stage {name}: {report['stages'][name]}")

    report['quota_after'] = client.governor.spent_today()
    report['units_spent'] = report['quota_after'] - report['quota_before']
    report['finished_at'] = utcnow()
    return report
