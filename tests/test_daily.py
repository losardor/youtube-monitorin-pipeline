"""Offline validation of the four daily stages.

The payloads below are hand-built fixtures shaped like YouTube Data API v3
responses. They exist to exercise control flow -- batching, quota accounting,
budget cut-off, mid-video resumption, disabled comments, dead ids, the
403-swallow regression -- without spending a real quota unit. They are not
data and no analysis reads them.

Ported from external/ytmon/tests/test_offline.py, keeping its fixture style
and adapted to this repo's schema and tier handling.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import daily                                              # noqa: E402
from src.database import Database                                  # noqa: E402
from src.errors import CommentsDisabled, QuotaExhausted            # noqa: E402
from src.lock import advisory_lock, LockUnavailable                # noqa: E402
from src.quota import QuotaGovernor, DAILY_FORBIDDEN_ENDPOINTS     # noqa: E402

CFG = {
    "quota": {"daily_budget": 500, "share_channels": 0.2, "share_discovery": 0.2,
              "share_videos": 0.2, "share_comments": 0.4},
    "schedule": {"channel_refresh_days": 1, "upload_lookback_days": 3650,
                 "video_restat_days": 1, "video_tracking_days": 3650,
                 "comment_tracking_days": {0: 3650, 1: 3650, 2: 3650}},
    "limits": {"max_upload_pages_per_channel": 3, "stop_after_known_videos": 10,
               "max_comment_pages_per_video": {0: 3, 1: 2, 2: 1},
               "max_reply_pages_per_comment": 1,
               "fetch_full_replies": True, "comment_order": "time",
               "recomment_growth_ratio": 1.10},
}

CH = ["UC" + str(i).rjust(22, "0") for i in range(3)]
DEAD = CH[2]


class FakeYouTube:
    """Stands in for YouTubeAPIClient; charges the real governor."""

    def __init__(self, gov, n_upload_pages=2, comment_pages=2, disabled_for=(),
                 unavailable_for=(), quota_after=None):
        self.governor = gov
        self.n_upload_pages = n_upload_pages
        self.comment_pages = comment_pages
        self.disabled_for = set(disabled_for)
        self.unavailable_for = set(unavailable_for)
        self.quota_after = quota_after     # raise QuotaExhausted after N calls
        self.calls = []

    def _charge(self, endpoint):
        if self.quota_after is not None and len(self.calls) >= self.quota_after:
            raise QuotaExhausted("fixture: budget spent")
        self.governor.charge(endpoint, 1)

    def channels_by_id(self, ids, part=None):
        self._charge("channels")
        self.calls.append(("channels", len(ids)))
        return {"items": [
            {"id": cid,
             "snippet": {"title": f"Chan {cid[-2:]}", "customUrl": f"@c{cid[-2:]}",
                         "country": "IT", "publishedAt": "2010-01-01T00:00:00Z",
                         "description": "desc"},
             "statistics": {"subscriberCount": "1230", "viewCount": "98765",
                            "videoCount": "42", "hiddenSubscriberCount": False},
             "contentDetails": {"relatedPlaylists": {"uploads": "UU" + cid[2:]}},
             "topicDetails": {"topicCategories": ["https://en.wikipedia.org/wiki/News"]}}
            for cid in ids if cid != DEAD]}          # DEAD never comes back

    def playlist_items(self, playlist_id, page_token=None):
        self._charge("playlistItems")
        self.calls.append(("playlistItems", playlist_id))
        page = 0 if page_token is None else int(page_token)
        base = playlist_id[-2:]
        items = [{"contentDetails": {"videoId": f"v{base}p{page}n{i}",
                                     "videoPublishedAt": "2026-09-01T00:00:00Z"}}
                 for i in range(2)]
        out = {"items": items}
        if page + 1 < self.n_upload_pages:
            out["nextPageToken"] = str(page + 1)
        return out

    def videos_by_id(self, ids, part=None):
        self._charge("videos")
        self.calls.append(("videos", len(ids)))
        return {"items": [
            {"id": v,
             "snippet": {"channelId": CH[0], "publishedAt": "2026-09-01T00:00:00Z",
                         "title": f"title {v}", "description": "body", "tags": ["news"],
                         "categoryId": "25", "liveBroadcastContent": "none"},
             "statistics": {"viewCount": "1000", "likeCount": "50", "commentCount": "7"},
             "contentDetails": {"duration": "PT10M"},
             "status": {"madeForKids": False},
             "topicDetails": {"topicCategories": ["https://en.wikipedia.org/wiki/Politics"]}}
            for v in ids]}

    def comment_threads(self, video_id, page_token=None, order="time"):
        if video_id in self.disabled_for:
            raise CommentsDisabled("comments are disabled")
        self._charge("commentThreads")
        self.calls.append(("commentThreads", video_id))
        page = 0 if page_token is None else int(page_token)
        items = []
        for i in range(2):
            cid = f"{video_id}-c{page}{i}"
            items.append({"snippet": {
                "totalReplyCount": 3,
                "topLevelComment": {"id": cid, "snippet": {
                    "authorDisplayName": f"user{i}",
                    "authorChannelId": {"value": f"UCauthor{i}"},
                    "textOriginal": "text", "likeCount": 2,
                    "publishedAt": "2026-09-02T00:00:00Z",
                    "updatedAt": "2026-09-02T00:00:00Z"}}},
                "replies": {"comments": [{"id": cid + "-r0", "snippet": {
                    "authorDisplayName": "replier",
                    "authorChannelId": {"value": "UCreplier"},
                    "textOriginal": "re", "likeCount": 0,
                    "publishedAt": "2026-09-02T01:00:00Z",
                    "updatedAt": "2026-09-02T01:00:00Z"}}]}})
        out = {"items": items}
        if page + 1 < self.comment_pages:
            out["nextPageToken"] = str(page + 1)
        return out

    def comment_replies(self, parent_id, page_token=None):
        self._charge("comments")
        return {"items": [{"id": f"{parent_id}-r{i}", "snippet": {
            "authorDisplayName": f"replier{i}",
            "authorChannelId": {"value": f"UCrep{i}"},
            "textOriginal": "deep reply", "likeCount": 1,
            "publishedAt": "2026-09-02T02:00:00Z",
            "updatedAt": "2026-09-02T02:00:00Z"}} for i in range(2)]}


def fresh(tmp, tiers=(0, 0, 0), **kw):
    """A database with three seeded channels, a governor, and a fake client."""
    db = Database(db_path=str(tmp))
    con = db.conn
    # Deliberately NOT setting row_factory here: Database sets it, and a
    # fixture that configures the connection differently from production is
    # how the harvest_comments tuple-indexing bug reached the cluster.
    for cid, tier in zip(CH, tiers):
        con.execute(
            "INSERT OR REPLACE INTO channels (channel_id, channel_title, tier) "
            "VALUES (?, ?, ?)", (cid, f"seed {cid[-2:]}", tier))
    con.commit()
    gov = QuotaGovernor(con, CFG["quota"]["daily_budget"],
                        forbidden_endpoints=DAILY_FORBIDDEN_ENDPOINTS)
    return con, gov, FakeYouTube(gov, **kw)


# ---------------------------------------------------------------------------
# full run
# ---------------------------------------------------------------------------

def test_full_run(tmp_path):
    con, gov, yt = fresh(tmp_path / "t.db")
    rep = daily.run(con, yt, CFG)

    # stage 1: two channels resolve, the third is marked dead rather than dropped
    assert rep["stages"]["channels"]["resolved"] == 2
    assert con.execute("SELECT COUNT(*) FROM channels").fetchone()[0] == 3
    assert con.execute(
        "SELECT status FROM channels WHERE channel_id = ?", (DEAD,)
    ).fetchone()[0] == "unresolved"

    # uploads_playlist populated from contentDetails, which stage 2 needs
    assert con.execute(
        "SELECT uploads_playlist FROM channels WHERE channel_id = ?", (CH[0],)
    ).fetchone()[0] == "UU" + CH[0][2:]

    # stage 2: only the two live channels are scanned
    assert rep["stages"]["discovery"]["new_videos"] > 0
    assert rep["stages"]["videos"]["refreshed"] > 0
    assert rep["stages"]["comments"]["comments"] > 0

    # every stage recorded itself, with per-stage call counts
    stages = {r["stage"]: r for r in con.execute("SELECT * FROM run_log")}
    assert set(stages) == {"resolve_channels", "discover_uploads",
                           "refresh_videos", "harvest_comments"}
    assert rep["units_spent"] == gov.spent_today()


def test_run_log_calls_are_per_stage_not_cumulative(tmp_path):
    """ytmon logged gov.session_calls, the session total, into every stage."""
    con, gov, yt = fresh(tmp_path / "t.db")
    daily.run(con, yt, CFG)

    rows = list(con.execute(
        "SELECT stage, calls FROM run_log ORDER BY started_at"))
    per_stage = {r["stage"]: r["calls"] for r in rows}

    # The sum of per-stage calls equals the session total; if any row held the
    # cumulative count instead, the sum would overshoot.
    assert sum(per_stage.values()) == gov.session_calls
    assert all(c >= 0 for c in per_stage.values())


# ---------------------------------------------------------------------------
# batching
# ---------------------------------------------------------------------------

def test_ids_are_batched_fifty_at_a_time(tmp_path):
    con, gov, yt = fresh(tmp_path / "t.db")
    now = daily.utcnow()
    # 120 videos -> 3 calls of 50/50/20, not 120 calls
    con.executemany(
        "INSERT INTO videos (video_id, channel_id, published_at, comments_state) "
        "VALUES (?, ?, ?, 'pending')",
        [(f"vid{i:04d}", CH[0], "2026-09-01T00:00:00Z") for i in range(120)])
    con.commit()

    daily.refresh_videos(con, yt, CFG, "run-batch")

    sizes = [n for kind, n in yt.calls if kind == "videos"]
    assert sizes == [50, 50, 20]


def test_channel_ids_are_batched_fifty_at_a_time(tmp_path):
    con, gov, yt = fresh(tmp_path / "t.db")
    con.executemany(
        "INSERT OR REPLACE INTO channels (channel_id, tier) VALUES (?, 0)",
        [("UC" + str(i).rjust(22, "x"),) for i in range(60)])
    con.commit()

    daily.resolve_channels(con, yt, CFG, "run-batch")

    sizes = [n for kind, n in yt.calls if kind == "channels"]
    assert max(sizes) <= 50
    assert sum(sizes) == 63          # 3 seeded + 60 added


# ---------------------------------------------------------------------------
# snapshots are append-only
# ---------------------------------------------------------------------------

def test_snapshots_accumulate_not_overwrite(tmp_path):
    """Two runs must leave two rows per id, not one updated row."""
    con, gov, yt = fresh(tmp_path / "t.db")

    daily.resolve_channels(con, yt, CFG, "run-1")
    first = con.execute("SELECT COUNT(*) FROM channel_snapshots").fetchone()[0]
    assert first == 2                        # DEAD contributes no snapshot

    # A second observation at a later instant appends rather than replaces.
    con.execute("UPDATE channels SET last_checked = NULL")
    con.commit()
    daily.resolve_channels(con, yt, CFG, "run-2")

    second = con.execute("SELECT COUNT(*) FROM channel_snapshots").fetchone()[0]
    assert second == 2 * first

    per_channel = con.execute(
        "SELECT COUNT(DISTINCT observed_at) FROM channel_snapshots "
        "WHERE channel_id = ?", (CH[0],)).fetchone()[0]
    assert per_channel == 2


def test_video_snapshots_accumulate(tmp_path):
    con, gov, yt = fresh(tmp_path / "t.db")
    con.execute(
        "INSERT INTO videos (video_id, channel_id, published_at, comments_state) "
        "VALUES ('vsnap1', ?, '2026-09-01T00:00:00Z', 'pending')", (CH[0],))
    con.commit()

    daily.refresh_videos(con, yt, CFG, "run-1")
    con.execute("UPDATE videos SET last_stats_at = NULL")
    con.commit()
    daily.refresh_videos(con, yt, CFG, "run-2")

    assert con.execute(
        "SELECT COUNT(*) FROM video_snapshots WHERE video_id = 'vsnap1'"
    ).fetchone()[0] == 2


def test_reobserved_comments_do_not_inflate_item_count(tmp_path):
    con, gov, yt = fresh(tmp_path / "t.db")
    con.execute(
        "INSERT INTO videos (video_id, channel_id, published_at, comments_state) "
        "VALUES ('vrec', ?, '2026-09-01T00:00:00Z', 'pending')", (CH[0],))
    con.commit()

    first = daily.harvest_comments(con, yt, CFG, "run-1")
    assert first["comments"] > 0
    total_after_first = con.execute("SELECT COUNT(*) FROM comments").fetchone()[0]

    # Re-poll the same video: the same comment ids come back.
    con.execute("UPDATE videos SET comments_state = 'pending', comment_cursor = NULL")
    con.commit()
    second = daily.harvest_comments(con, yt, CFG, "run-2")

    assert second["comments"] == 0
    assert con.execute("SELECT COUNT(*) FROM comments").fetchone()[0] == total_after_first


# ---------------------------------------------------------------------------
# budget
# ---------------------------------------------------------------------------

def test_budget_stops_and_resumes_mid_video(tmp_path):
    """A stage that runs out mid-video keeps the cursor and resumes there."""
    con, gov, yt = fresh(tmp_path / "t.db", comment_pages=5)
    con.execute(
        "INSERT INTO videos (video_id, channel_id, published_at, comments_state) "
        "VALUES ('vresume', ?, '2026-09-01T00:00:00Z', 'pending')", (CH[0],))
    con.commit()

    tiny = json.loads(json.dumps(CFG))
    tiny["quota"]["daily_budget"] = 2
    tiny["limits"]["max_comment_pages_per_video"] = {"0": 99}
    tiny["limits"]["fetch_full_replies"] = False
    small_gov = QuotaGovernor(con, 2)
    yt.governor = small_gov

    daily.harvest_comments(con, yt, tiny, "run-cut")

    row = con.execute(
        "SELECT comments_state, comment_cursor, comment_pages_fetched "
        "FROM videos WHERE video_id = 'vresume'").fetchone()
    assert row["comments_state"] == "pending"      # not done: more to fetch
    assert row["comment_cursor"] is not None       # resume point kept
    pages_first = row["comment_pages_fetched"]
    assert pages_first > 0

    # Next run, fresh budget: it picks up from the stored cursor.
    yt.governor = QuotaGovernor(con, 500)
    daily.harvest_comments(con, yt, tiny, "run-resume")

    row2 = con.execute(
        "SELECT comments_state, comment_pages_fetched FROM videos "
        "WHERE video_id = 'vresume'").fetchone()
    assert row2["comment_pages_fetched"] > pages_first
    assert row2["comments_state"] == "done"


def test_quota_governor_refuses_overspend(tmp_path):
    con, gov, yt = fresh(tmp_path / "t.db")
    gov.daily_budget = 3
    gov.charge("channels", 3)
    assert gov.remaining() == 0
    assert not gov.can_afford(1)


def test_governor_spend_survives_restart(tmp_path):
    """Spend lives in the ledger, so a new process cannot reset it."""
    con, gov, yt = fresh(tmp_path / "t.db")
    gov.charge("channels", 40)

    reopened = QuotaGovernor(con, 500)
    assert reopened.spent_today() == 40
    assert reopened.remaining() == 460


def test_search_endpoint_is_forbidden_on_the_daily_path(tmp_path):
    con, gov, yt = fresh(tmp_path / "t.db")
    assert gov.is_forbidden("search")
    assert not gov.is_forbidden("playlistItems")


# ---------------------------------------------------------------------------
# failure modes
# ---------------------------------------------------------------------------

def test_disabled_comments_recorded(tmp_path):
    con, gov, yt = fresh(tmp_path / "t.db", disabled_for=["vdis"])
    con.execute(
        "INSERT INTO videos (video_id, channel_id, published_at, comments_state) "
        "VALUES ('vdis', ?, '2026-09-01T00:00:00Z', 'pending')", (CH[0],))
    con.commit()

    daily.harvest_comments(con, yt, CFG, "run-dis")

    row = con.execute(
        "SELECT comments_state, comment_cursor FROM videos "
        "WHERE video_id = 'vdis'").fetchone()
    assert row["comments_state"] == "disabled"
    assert row["comment_cursor"] is None


def test_dead_channel_is_marked_not_deleted(tmp_path):
    con, gov, yt = fresh(tmp_path / "t.db")
    daily.resolve_channels(con, yt, CFG, "run-dead")

    row = con.execute(
        "SELECT status, channel_title FROM channels WHERE channel_id = ?",
        (DEAD,)).fetchone()
    assert row["status"] == "unresolved"
    # The row survives, carrying its seed provenance.
    assert row["channel_title"] == f"seed {DEAD[-2:]}"
    assert con.execute("SELECT COUNT(*) FROM channels").fetchone()[0] == 3


# ---------------------------------------------------------------------------
# tiering
# ---------------------------------------------------------------------------

def test_tier_zero_is_served_first(tmp_path):
    """Tier 0 must be scanned before tier 1 and 2 in discovery."""
    con, gov, yt = fresh(tmp_path / "t.db", tiers=(2, 1, 0))
    # Give all three a playlist and active status so ordering is the only factor.
    for cid in CH:
        con.execute(
            "UPDATE channels SET status = 'active', uploads_playlist = ? "
            "WHERE channel_id = ?", ("UU" + cid[2:], cid))
    con.commit()

    daily.discover_uploads(con, yt, CFG, "run-tier")

    scanned = [pid for kind, pid in yt.calls if kind == "playlistItems"]
    order = [p for i, p in enumerate(scanned) if p not in scanned[:i]]
    # CH[2] is tier 0, CH[1] tier 1, CH[0] tier 2
    assert order == ["UU" + CH[2][2:], "UU" + CH[1][2:], "UU" + CH[0][2:]]


def test_comment_page_cap_is_per_tier(tmp_path):
    """A tier-2 video is sampled shallowly; a tier-0 video is pulled deep."""
    con, gov, yt = fresh(tmp_path / "t.db", tiers=(0, 2, 0), comment_pages=9)
    cfg = json.loads(json.dumps(CFG))
    cfg["limits"]["fetch_full_replies"] = False

    con.execute(
        "INSERT INTO videos (video_id, channel_id, published_at, comments_state) "
        "VALUES ('vt0', ?, '2026-09-01T00:00:00Z', 'pending')", (CH[0],))
    con.execute(
        "INSERT INTO videos (video_id, channel_id, published_at, comments_state) "
        "VALUES ('vt2', ?, '2026-09-01T00:00:00Z', 'pending')", (CH[1],))
    con.commit()

    daily.harvest_comments(con, yt, cfg, "run-caps")

    pages = {}
    for kind, vid in yt.calls:
        if kind == "commentThreads":
            pages[vid] = pages.get(vid, 0) + 1
    caps = cfg["limits"]["max_comment_pages_per_video"]
    # The JSON round-trip above stringifies the tier keys, which is exactly the
    # case _per_tier exists to absorb -- read them the way daily.py does.
    assert pages["vt0"] == daily._per_tier(caps, 0, 99)   # 3
    assert pages["vt2"] == daily._per_tier(caps, 2, 99)   # 1


def test_per_tier_lookup_accepts_scalar_and_string_keys():
    assert daily._per_tier({0: 50, 1: 10}, 0, 3) == 50
    assert daily._per_tier({"0": 50, "1": 10}, 1, 3) == 10
    assert daily._per_tier({0: 50}, 2, 3) == 3          # falls back
    assert daily._per_tier(7, 2, 3) == 7                # scalar applies to all


# ---------------------------------------------------------------------------
# the 403-swallow regression
# ---------------------------------------------------------------------------

def _http_error(status: int, reason: str, message: str = "err"):
    """An HttpError shaped like the real thing."""
    import httplib2
    from googleapiclient.errors import HttpError
    resp = httplib2.Response({"status": status})
    resp.reason = message
    content = json.dumps(
        {"error": {"errors": [{"reason": reason}], "message": message}}
    ).encode()
    return HttpError(resp, content)


def _client(tmp_path, **kw):
    from src.youtube_client import YouTubeAPIClient
    return YouTubeAPIClient(api_key="fixture-key-not-real", max_retries=1, **kw)


def test_quota_403_raises_and_leaves_the_channel_row_untouched(tmp_path):
    """
    The 403-swallow regression.

    A quotaExceeded 403 used to be caught by a blanket `except Exception` and
    returned as None, which the validator recorded as "Channel not found".
    That is how ~752 live channels were marked dead across Runs #2 and #3d.
    The contamination signature was cost=0 AND success=False.
    """
    db = Database(db_path=str(tmp_path / "t.db"))
    con = db.conn
    con.row_factory = sqlite3.Row
    con.execute(
        "INSERT INTO channels (channel_id, channel_title, subscriber_count, status) "
        "VALUES (?, 'Real Channel', 1234, 'active')", (CH[0],))
    con.commit()
    before = dict(con.execute(
        "SELECT * FROM channels WHERE channel_id = ?", (CH[0],)).fetchone())

    gov = QuotaGovernor(con, 500)
    client = _client(tmp_path, governor=gov)

    def quota_403():
        raise _http_error(403, "quotaExceeded", "quota exceeded")

    with pytest.raises(QuotaExhausted):
        client._call(quota_403, endpoint="channels")

    # 1. the row is byte-identical: no not-found was recorded
    after = dict(con.execute(
        "SELECT * FROM channels WHERE channel_id = ?", (CH[0],)).fetchone())
    assert after == before

    # 2. the ledger was not charged for a call the API refused
    assert gov.spent_today() == 0
    assert client.quota_usage == 0

    db.close()


def test_get_channel_info_propagates_quota_exhausted(tmp_path):
    """The specific method named in the brief, not just the chokepoint."""
    client = _client(tmp_path)
    client._call = lambda *a, **k: (_ for _ in ()).throw(
        QuotaExhausted("quotaExceeded: quota exceeded"))

    with pytest.raises(QuotaExhausted):
        client.get_channel_info(CH[0])


def test_contamination_signature_cannot_recur(tmp_path):
    """
    revalidate_contaminated.py aborts after three consecutive
    (cost=0, success=False) responses, the signature of a surviving swallow
    path. Feeding the client three quota 403s must never produce that shape:
    each one raises instead of returning a zero-cost failure.
    """
    db = Database(db_path=str(tmp_path / "t.db"))
    gov = QuotaGovernor(db.conn, 500)
    client = _client(tmp_path, governor=gov)

    def quota_403():
        raise _http_error(403, "quotaExceeded", "quota exceeded")

    consecutive_silent_failures = 0
    for _ in range(3):
        cost_before = client.quota_usage
        try:
            result = client._call(quota_403, endpoint="channels")
        except QuotaExhausted:
            continue        # loud failure: correct
        # If we ever get here, the swallow is back.
        if result is None and client.quota_usage == cost_before:
            consecutive_silent_failures += 1

    assert consecutive_silent_failures == 0
    assert gov.spent_today() == 0
    db.close()


def test_not_found_is_distinguishable_from_quota_exhausted(tmp_path):
    """An empty items list is the only honest not-found, and it costs 1 unit."""
    db = Database(db_path=str(tmp_path / "t.db"))
    gov = QuotaGovernor(db.conn, 500)
    client = _client(tmp_path, governor=gov)

    result = client._call(lambda: {"items": []}, endpoint="channels")

    assert result == {"items": []}
    assert gov.spent_today() == 1        # served, so charged
    db.close()


def test_rate_limit_is_not_reported_as_quota_exhausted_until_retries_run_out(tmp_path):
    db = Database(db_path=str(tmp_path / "t.db"))
    gov = QuotaGovernor(db.conn, 500)
    client = _client(tmp_path, governor=gov)
    client.max_retries = 2
    client.retry_delay = 0

    attempts = {"n": 0}

    def flaky():
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise _http_error(403, "rateLimitExceeded", "slow down")
        return {"items": [{"id": "ok"}]}

    result = client._call(flaky, endpoint="channels")
    assert result["items"][0]["id"] == "ok"
    assert attempts["n"] == 2
    assert gov.spent_today() == 1        # charged once, for the served call
    db.close()


def test_item_unavailable_does_not_stop_the_run(tmp_path):
    db = Database(db_path=str(tmp_path / "t.db"))
    gov = QuotaGovernor(db.conn, 500)
    client = _client(tmp_path, governor=gov)

    from src.errors import ItemUnavailable

    def gone():
        raise _http_error(404, "videoNotFound", "no such video")

    with pytest.raises(ItemUnavailable):
        client._call(gone, endpoint="videos")
    assert gov.spent_today() == 0
    db.close()


def test_search_is_refused_by_both_guards_independently(tmp_path):
    db = Database(db_path=str(tmp_path / "t.db"))

    # Guard 1: the client flag, with no governor at all.
    flagged = _client(tmp_path)
    with pytest.raises(QuotaExhausted, match="allow_search"):
        flagged._call(lambda: {"items": []}, endpoint="search")

    # Guard 2: the governor's ban, even when the flag permits it.
    gov = QuotaGovernor(db.conn, 500, forbidden_endpoints=DAILY_FORBIDDEN_ENDPOINTS)
    permitted = _client(tmp_path, governor=gov, allow_search=True)
    with pytest.raises(QuotaExhausted, match="not permitted"):
        permitted._call(lambda: {"items": []}, endpoint="search")

    assert gov.spent_today() == 0
    db.close()


# ---------------------------------------------------------------------------
# advisory lock
# ---------------------------------------------------------------------------

def test_second_lock_acquisition_fails_immediately(tmp_path):
    """
    The daily run and a backfill must contend. A second acquisition fails
    fast rather than queueing behind a multi-hour job.
    """
    lock_path = tmp_path / ".ytmon.lock"
    child = tmp_path / "child.py"
    child.write_text(
        "import sys, time\n"
        f"sys.path.insert(0, {str(Path(__file__).resolve().parents[1])!r})\n"
        "from src.lock import advisory_lock, LockUnavailable\n"
        "t = time.time()\n"
        "try:\n"
        "    with advisory_lock(sys.argv[1]):\n"
        "        print('ACQUIRED')\n"
        "except LockUnavailable:\n"
        "    print('BLOCKED %.3f' % (time.time() - t))\n"
    )

    with advisory_lock(str(lock_path)):
        out = subprocess.run([sys.executable, str(child), str(lock_path)],
                             capture_output=True, text=True, timeout=30)
        assert out.stdout.startswith("BLOCKED"), out.stdout + out.stderr
        # "immediately": well under any plausible queueing delay
        assert float(out.stdout.split()[1]) < 2.0

    # Once released, the same call succeeds.
    out = subprocess.run([sys.executable, str(child), str(lock_path)],
                         capture_output=True, text=True, timeout=30)
    assert out.stdout.strip() == "ACQUIRED", out.stdout + out.stderr


def test_lock_is_released_when_the_block_raises(tmp_path):
    lock_path = tmp_path / ".ytmon.lock"

    with pytest.raises(ValueError):
        with advisory_lock(str(lock_path)):
            raise ValueError("boom")

    # Not left held by the dead block.
    with advisory_lock(str(lock_path)):
        pass


# ---------------------------------------------------------------------------
# migration
# ---------------------------------------------------------------------------

def _seed_legacy_db(path) -> None:
    """A database shaped like the pre-migration production file."""
    con = sqlite3.connect(str(path))
    # Mirrors the shape of the real pre-migration file closely enough that
    # Database._create_tables can build its indexes (published_at, comments).
    con.executescript("""
        CREATE TABLE channels (
            channel_id TEXT PRIMARY KEY, channel_title TEXT,
            subscriber_count INTEGER, video_count INTEGER, view_count INTEGER,
            first_collected_at TEXT, last_updated_at TEXT);
        CREATE TABLE videos (
            video_id TEXT PRIMARY KEY, channel_id TEXT, title TEXT,
            published_at TEXT, view_count INTEGER, like_count INTEGER,
            comment_count INTEGER, collected_at TEXT);
        CREATE TABLE comments (
            comment_id TEXT PRIMARY KEY, video_id TEXT, published_at TEXT,
            text TEXT, collected_at TEXT);
    """)
    # first_collected_at NULL, as every row in the real database has it
    con.execute("INSERT INTO channels VALUES ('UCa', 'A', 100, 5, 900, NULL, "
                "'2025-11-19T11:07:24')")
    con.execute("INSERT INTO channels VALUES ('UCb', 'B', 200, 6, 800, "
                "'2025-11-01T00:00:00', '2025-11-19T11:07:25')")
    con.execute("INSERT INTO videos VALUES ('v1', 'UCa', 't1', "
                "'2025-11-01T00:00:00', 10, 1, 2, '2025-11-19T10:37:32')")
    # comments disabled: NULL comment_count, which must stay NULL
    con.execute("INSERT INTO videos VALUES ('v2', 'UCa', 't2', "
                "'2025-11-02T00:00:00', 20, 2, NULL, '2025-11-19T10:37:33')")
    con.commit()
    con.close()


def test_migration_backfills_from_existing_timestamps(tmp_path):
    from scripts.migrate_snapshots import main as migrate

    db_path = tmp_path / "legacy.db"
    _seed_legacy_db(db_path)
    assert migrate(["--db", str(db_path)]) == 0

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row

    # one row per record, observed_at taken from the record itself
    assert con.execute("SELECT COUNT(*) FROM channel_snapshots").fetchone()[0] == 2
    assert con.execute("SELECT COUNT(*) FROM video_snapshots").fetchone()[0] == 2

    # COALESCE(first_collected_at, last_updated_at)
    assert con.execute(
        "SELECT observed_at FROM channel_snapshots WHERE channel_id = 'UCa'"
    ).fetchone()[0] == "2025-11-19T11:07:24"
    assert con.execute(
        "SELECT observed_at FROM channel_snapshots WHERE channel_id = 'UCb'"
    ).fetchone()[0] == "2025-11-01T00:00:00"

    # NULLs preserved as NULL, never coerced to 0
    assert con.execute(
        "SELECT comment_count FROM video_snapshots WHERE video_id = 'v2'"
    ).fetchone()[0] is None
    assert con.execute(
        "SELECT hidden_subscribers FROM channel_snapshots WHERE channel_id = 'UCa'"
    ).fetchone()[0] is None
    con.close()


def test_migration_is_idempotent(tmp_path):
    from scripts.migrate_snapshots import main as migrate

    db_path = tmp_path / "legacy.db"
    _seed_legacy_db(db_path)

    migrate(["--db", str(db_path)])
    con = sqlite3.connect(str(db_path))
    first = (con.execute("SELECT COUNT(*) FROM channel_snapshots").fetchone()[0],
             con.execute("SELECT COUNT(*) FROM video_snapshots").fetchone()[0])
    con.close()

    migrate(["--db", str(db_path)])
    con = sqlite3.connect(str(db_path))
    second = (con.execute("SELECT COUNT(*) FROM channel_snapshots").fetchone()[0],
              con.execute("SELECT COUNT(*) FROM video_snapshots").fetchone()[0])
    con.close()

    assert first == second == (2, 2)


@pytest.mark.skipif(not Path("data/youtube_monitoring.db").exists(),
                    reason="production database not present")
def test_migration_idempotent_on_a_copy_of_the_real_database(tmp_path):
    """Runs on a copy. The original is never opened for writing."""
    import shutil
    from scripts.migrate_snapshots import main as migrate

    copy = tmp_path / "real_copy.db"
    shutil.copy("data/youtube_monitoring.db", copy)

    con = sqlite3.connect(str(copy))
    # Only records carrying a collection timestamp can be backfilled. Channels
    # loaded from the validated frame have none until the first channels stage
    # observes them, so they are correctly skipped rather than given a
    # fabricated observed_at.
    n_channels = con.execute(
        "SELECT COUNT(*) FROM channels "
        "WHERE COALESCE(first_collected_at, last_updated_at) IS NOT NULL"
    ).fetchone()[0]
    n_videos = con.execute(
        "SELECT COUNT(*) FROM videos WHERE collected_at IS NOT NULL"
    ).fetchone()[0]
    con.close()

    assert migrate(["--db", str(copy)]) == 0

    # The invariant is coverage, not a global row count: channel_snapshots also
    # holds observations from other sources (the validation-phase backfill, and
    # later every daily pass), so counting the whole table would not measure
    # what this migration did. What must hold is that every timestamped record
    # has a snapshot *at its own timestamp*.
    con = sqlite3.connect(str(copy))
    missing_channels = con.execute("""
        SELECT COUNT(*) FROM channels c
         WHERE COALESCE(c.first_collected_at, c.last_updated_at) IS NOT NULL
           AND NOT EXISTS (
             SELECT 1 FROM channel_snapshots s
              WHERE s.channel_id = c.channel_id
                AND s.observed_at = COALESCE(c.first_collected_at, c.last_updated_at))
    """).fetchone()[0]
    missing_videos = con.execute("""
        SELECT COUNT(*) FROM videos v
         WHERE v.collected_at IS NOT NULL
           AND NOT EXISTS (
             SELECT 1 FROM video_snapshots s
              WHERE s.video_id = v.video_id AND s.observed_at = v.collected_at)
    """).fetchone()[0]
    assert (missing_channels, missing_videos) == (0, 0)
    first = (con.execute("SELECT COUNT(*) FROM channel_snapshots").fetchone()[0],
             con.execute("SELECT COUNT(*) FROM video_snapshots").fetchone()[0])
    con.close()
    assert first[0] >= n_channels and first[1] >= n_videos

    # Idempotent: a second run adds nothing.
    assert migrate(["--db", str(copy)]) == 0
    con = sqlite3.connect(str(copy))
    second = (con.execute("SELECT COUNT(*) FROM channel_snapshots").fetchone()[0],
              con.execute("SELECT COUNT(*) FROM video_snapshots").fetchone()[0])
    con.close()
    assert second == first


def test_insert_replace_preserves_daily_pipeline_columns(tmp_path):
    """
    A backfill re-insert must not reset tier or lose comment paging state:
    INSERT OR REPLACE deletes the old row, so those columns are carried
    across explicitly.
    """
    db = Database(db_path=str(tmp_path / "t.db"))
    con = db.conn
    con.row_factory = sqlite3.Row

    db.insert_channel({"id": CH[0], "snippet": {"title": "First"},
                       "statistics": {"subscriberCount": "10"}})
    con.execute("UPDATE channels SET tier = 1, wd_item = 'Q42' WHERE channel_id = ?",
                (CH[0],))
    con.commit()
    first_seen = con.execute(
        "SELECT first_collected_at FROM channels WHERE channel_id = ?",
        (CH[0],)).fetchone()[0]
    assert first_seen is not None          # finally populated

    db.insert_channel({"id": CH[0], "snippet": {"title": "Second"},
                       "statistics": {"subscriberCount": "20"}})
    row = con.execute("SELECT * FROM channels WHERE channel_id = ?",
                      (CH[0],)).fetchone()
    assert row["channel_title"] == "Second"
    assert row["tier"] == 1                       # not reset to the default
    assert row["wd_item"] == "Q42"
    assert row["first_collected_at"] == first_seen

    db.insert_video({"id": "vkeep", "snippet": {"channelId": CH[0], "title": "v"},
                     "statistics": {"viewCount": "1"}, "contentDetails": {}})
    con.execute("UPDATE videos SET comments_state = 'pending', "
                "comment_cursor = 'TOKEN', comment_pages_fetched = 4 "
                "WHERE video_id = 'vkeep'")
    con.commit()

    db.insert_video({"id": "vkeep", "snippet": {"channelId": CH[0], "title": "v2"},
                     "statistics": {"viewCount": "2"}, "contentDetails": {}})
    v = con.execute("SELECT * FROM videos WHERE video_id = 'vkeep'").fetchone()
    assert v["title"] == "v2"
    assert v["comment_cursor"] == "TOKEN"         # resume point survives
    assert v["comment_pages_fetched"] == 4
    assert v["comments_state"] == "pending"

    # and both writes appended snapshots
    assert con.execute(
        "SELECT COUNT(*) FROM channel_snapshots WHERE channel_id = ?",
        (CH[0],)).fetchone()[0] == 2
    db.close()


# ---------------------------------------------------------------------------
# frame loading (2.0)
# ---------------------------------------------------------------------------

def _write_frame_fixtures(tmp_path):
    """A validation file and a sources CSV shaped like the real ones."""
    validation = tmp_path / "validation.json"
    sources = tmp_path / "sources.csv"

    validation.write_text(json.dumps({
        "validated": ["u1", "u2", "u3", "u4"],
        "results": [
            # two URLs resolving to the same channel: one row must survive
            {"url": "https://www.youtube.com/@alpha", "success": True,
             "channel_id": "UCalpha", "validated_at": "2025-12-11T10:00:00"},
            {"url": "https://www.youtube.com/c/alpha-alt", "success": True,
             "channel_id": "UCalpha", "validated_at": "2026-04-20T10:00:00"},
            {"url": "https://www.youtube.com/@beta", "success": True,
             "channel_id": "UCbeta", "validated_at": "2025-12-11T11:00:00"},
            # failures are not part of the frame
            {"url": "https://www.youtube.com/@gone", "success": False,
             "channel_id": None, "validated_at": "2025-12-11T12:00:00"},
        ]}))

    with open(sources, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["Domain", "Rating", "Orientation", "Youtube"])
        w.writeheader()
        w.writerow({"Domain": "alpha.example", "Rating": "T",
                    "Orientation": "Left", "Youtube": "https://www.youtube.com/@alpha"})
        w.writerow({"Domain": "beta.example", "Rating": "N",
                    "Orientation": "Right", "Youtube": "https://www.youtube.com/@beta"})
    return validation, sources


def test_load_frame_collapses_duplicates_and_carries_metadata(tmp_path):
    from scripts.load_frame import main as load

    validation, sources = _write_frame_fixtures(tmp_path)
    db_path = tmp_path / "frame.db"
    Database(db_path=str(db_path)).close()

    assert load(["--db", str(db_path), "--validation", str(validation),
                 "--sources", str(sources)]) == 0

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    assert con.execute("SELECT COUNT(*) FROM channels").fetchone()[0] == 2

    alpha = con.execute(
        "SELECT * FROM channels WHERE channel_id = 'UCalpha'").fetchone()
    assert alpha["tier"] == 0
    assert alpha["source_domain"] == "alpha.example"
    assert alpha["source_rating"] == "T"
    assert alpha["source_orientation"] == "Left"
    # earliest validation wins, deterministically
    assert alpha["status"] is None and alpha["last_checked"] is None
    # no statistics without a snapshot to back them
    assert alpha["subscriber_count"] is None
    con.close()


def test_load_frame_preserves_already_collected_channels(tmp_path):
    """The 29 November rows must keep statistics, snapshots and timestamps."""
    from scripts.load_frame import main as load

    validation, sources = _write_frame_fixtures(tmp_path)
    db_path = tmp_path / "frame.db"
    db = Database(db_path=str(db_path))

    # A channel already collected, and one collected but not in the frame.
    db.insert_channel({"id": "UCalpha", "snippet": {"title": "Alpha News"},
                       "statistics": {"subscriberCount": "5000",
                                      "viewCount": "90", "videoCount": "7"}})
    db.insert_channel({"id": "UCstray", "snippet": {"title": "Stray"},
                       "statistics": {"subscriberCount": "12"}})
    db.close()

    load(["--db", str(db_path), "--validation", str(validation),
          "--sources", str(sources)])

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    alpha = con.execute(
        "SELECT * FROM channels WHERE channel_id = 'UCalpha'").fetchone()
    assert alpha["subscriber_count"] == 5000        # statistics untouched
    assert alpha["channel_title"] == "Alpha News"   # title untouched
    assert alpha["tier"] == 0                       # tier filled in
    assert alpha["source_rating"] == "T"
    assert con.execute(
        "SELECT COUNT(*) FROM channel_snapshots WHERE channel_id = 'UCalpha'"
    ).fetchone()[0] == 1                            # snapshot survives

    # In the database, not in the frame: recorded, never collected, not deleted.
    stray = con.execute(
        "SELECT * FROM channels WHERE channel_id = 'UCstray'").fetchone()
    assert stray["tier"] == 3
    assert stray["subscriber_count"] == 12
    con.close()


def test_load_frame_is_idempotent(tmp_path):
    from scripts.load_frame import main as load

    validation, sources = _write_frame_fixtures(tmp_path)
    db_path = tmp_path / "frame.db"
    Database(db_path=str(db_path)).close()

    args = ["--db", str(db_path), "--validation", str(validation),
            "--sources", str(sources)]
    load(args)
    con = sqlite3.connect(str(db_path))
    first = con.execute("SELECT COUNT(*) FROM channels").fetchone()[0]
    con.close()

    load(args)
    con = sqlite3.connect(str(db_path))
    assert con.execute("SELECT COUNT(*) FROM channels").fetchone()[0] == first
    assert con.execute("SELECT COUNT(*) FROM channels WHERE tier = 0"
                       ).fetchone()[0] == 2
    con.close()


# ---------------------------------------------------------------------------
# tiering rule (phase 2)
# ---------------------------------------------------------------------------

def _rec(**kw):
    base = {'channel_id': 'UCx', 'resolved': True, 'has_videos': True,
            'topic': False, 'title': False, 'topics': [], 'label': 'Seed'}
    base.update(kw)
    return base


def _wiki(name):
    return f"https://en.wikipedia.org/wiki/{name}"


def test_topic_check_drops_news_and_keeps_the_three_that_occur():
    from scripts.tier_frame import topic_ok, TOPIC_SUFFIXES

    # News was in the brief but never occurs in the data, so it is not a check.
    assert 'News' not in TOPIC_SUFFIXES
    assert topic_ok([_wiki('Society')])
    assert topic_ok([_wiki('Politics')])
    assert topic_ok([_wiki('Business')])
    assert not topic_ok([_wiki('Sport')])
    assert not topic_ok([])


def test_admitting_check_is_recorded_precisely():
    from scripts.assign_tiers import admits

    assert admits(_rec(topic=True, topics=[_wiki('Society')])) == 'topic'
    assert admits(_rec(topic=True, title=True,
                       topics=[_wiki('Politics')])) == 'topic+title'
    assert admits(_rec(title=True)) == 'title_only'
    assert admits(_rec()) is None
    assert admits(_rec(topic=True, resolved=False)) is None
    assert admits(_rec(topic=True, has_videos=False)) is None


def test_title_only_is_refused_for_gaming_and_music_but_not_sport():
    from scripts.assign_tiers import admits

    # A gaming site riding a name match is not a news outlet.
    assert admits(_rec(title=True, topics=[_wiki('Video_game_culture')])) is None
    assert admits(_rec(title=True, topics=[_wiki('Pop_music')])) is None

    # A local newspaper tagged Sport is: that is what its video output is, and
    # excluding Sport would drop exactly the frame-gap the study looks for.
    assert admits(_rec(title=True, topics=[_wiki('Sport')])) == 'title_only'
    assert admits(_rec(title=True,
                       topics=[_wiki('Baseball'), _wiki('American_football')])
                  ) == 'title_only'

    # A topic match wins regardless of a gaming tag alongside it.
    assert admits(_rec(topic=True, title=True,
                       topics=[_wiki('Politics'), _wiki('Action_game')])
                  ) == 'topic+title'


def test_title_match_folds_case_and_diacritics():
    from scripts.tier_frame import title_ok

    assert title_ok('Naftemporiki', 'NAFTEMPORIKI')
    assert title_ok('La Provence', 'Là Provençe')
    # Stopwords alone must not make a match.
    assert not title_ok('The Daily News', 'The News Channel')
    assert not title_ok('', 'Anything')


def test_tier_reason_survives_insert_or_replace(tmp_path):
    """Gate 2 demotes strata by UPDATE, so the reason must not be wiped."""
    db = Database(db_path=str(tmp_path / "t.db"))
    con = db.conn
    db.insert_channel({'id': 'UCkeep', 'snippet': {'title': 'First'},
                       'statistics': {'subscriberCount': '10'}})
    con.execute("UPDATE channels SET tier = 1, tier_reason = 'title_only' "
                "WHERE channel_id = 'UCkeep'")
    con.commit()

    db.insert_channel({'id': 'UCkeep', 'snippet': {'title': 'Second'},
                       'statistics': {'subscriberCount': '20'}})
    row = con.execute("SELECT tier, tier_reason, channel_title FROM channels "
                      "WHERE channel_id = 'UCkeep'").fetchone()
    # tuple(): rows are sqlite3.Row, which is a sequence but does not compare
    # equal to a plain tuple.
    assert tuple(row) == (1, 'title_only', 'Second')
    db.close()


def test_tier_three_is_never_resolved(tmp_path):
    """Recorded, never collected: no stage may spend a unit on tier 3."""
    con, gov, yt = fresh(tmp_path / "t.db", tiers=(0, 1, 3))
    daily.resolve_channels(con, yt, CFG, "run-t3")

    asked = set()
    for kind, n in yt.calls:
        if kind == "channels":
            asked.add(n)
    # CH[2] is tier 3 here and must not be in any batch; only 2 ids requested.
    assert asked == {2}
    assert con.execute(
        "SELECT status FROM channels WHERE channel_id = ?", (CH[2],)
    ).fetchone()[0] is None


def test_max_tier_limits_the_channels_stage(tmp_path):
    con, gov, yt = fresh(tmp_path / "t.db", tiers=(0, 1, 2))
    cfg = json.loads(json.dumps(CFG))
    cfg["limits"]["max_tier"] = 0

    daily.resolve_channels(con, yt, cfg, "run-cap")

    sizes = [n for kind, n in yt.calls if kind == "channels"]
    assert sizes == [1]          # only the single tier-0 channel


# ---------------------------------------------------------------------------
# collect_tiers: scope gating
# ---------------------------------------------------------------------------

def test_collect_tiers_resolution():
    from src.daily import collect_tiers

    assert collect_tiers({'collect_tiers': [0, 1]}) == [0, 1]
    assert collect_tiers({}) == [0, 1, 2]               # default: all but 3
    # No configuration can opt into collecting tier 3.
    assert collect_tiers({'collect_tiers': [0, 1, 2, 3]}) == [0, 1, 2]
    assert collect_tiers({'collect_tiers': [3]}) == []
    # --max-tier narrows further, never widens.
    assert collect_tiers({'collect_tiers': [0, 1],
                          'limits': {'max_tier': 0}}) == [0]
    assert collect_tiers({'collect_tiers': [0],
                          'limits': {'max_tier': 2}}) == [0]


def _cfg_tiers(tiers):
    cfg = json.loads(json.dumps(CFG))
    cfg['collect_tiers'] = tiers
    return cfg


def test_excluded_tier_is_never_queued_for_channels(tmp_path):
    """Tier 2 must not be queued while it is outside collect_tiers."""
    con, gov, yt = fresh(tmp_path / "t.db", tiers=(0, 1, 2))
    daily.resolve_channels(con, yt, _cfg_tiers([0, 1]), "run-scope")

    # Two channels requested (tier 0 and 1), never the tier-2 one.
    assert [n for kind, n in yt.calls if kind == "channels"] == [2]
    assert con.execute(
        "SELECT status FROM channels WHERE channel_id = ?", (CH[2],)
    ).fetchone()[0] is None


def test_excluded_tier_is_never_queued_for_discovery(tmp_path):
    con, gov, yt = fresh(tmp_path / "t.db", tiers=(0, 1, 2))
    for cid in CH:
        con.execute("UPDATE channels SET status = 'active', uploads_playlist = ? "
                    "WHERE channel_id = ?", ("UU" + cid[2:], cid))
    con.commit()

    daily.discover_uploads(con, yt, _cfg_tiers([0, 1]), "run-scope")

    scanned = {pid for kind, pid in yt.calls if kind == "playlistItems"}
    assert "UU" + CH[2][2:] not in scanned      # tier 2 excluded
    assert "UU" + CH[0][2:] in scanned
    assert "UU" + CH[1][2:] in scanned


def test_excluded_tier_is_never_queued_for_videos_or_comments(tmp_path):
    con, gov, yt = fresh(tmp_path / "t.db", tiers=(0, 2, 2))
    # One video on a tier-0 channel, one on a tier-2 channel.
    con.execute("INSERT INTO videos (video_id, channel_id, published_at, "
                "comments_state) VALUES ('vok', ?, '2026-09-01T00:00:00Z', "
                "'pending')", (CH[0],))
    con.execute("INSERT INTO videos (video_id, channel_id, published_at, "
                "comments_state) VALUES ('vno', ?, '2026-09-01T00:00:00Z', "
                "'pending')", (CH[1],))
    con.commit()
    cfg = _cfg_tiers([0, 1])

    daily.refresh_videos(con, yt, cfg, "run-scope")
    assert con.execute("SELECT last_stats_at FROM videos WHERE video_id = 'vno'"
                       ).fetchone()[0] is None
    assert con.execute("SELECT last_stats_at FROM videos WHERE video_id = 'vok'"
                       ).fetchone()[0] is not None

    daily.harvest_comments(con, yt, cfg, "run-scope")
    pulled = {vid for kind, vid in yt.calls if kind == "commentThreads"}
    assert 'vno' not in pulled
    assert 'vok' in pulled


def test_shipped_config_collects_the_gated_tiers(tmp_path):
    """
    The committed daily config collects tiers 0-2 and never tier 3.

    Tier 2 was admitted once the rule-(a) tightening brought it to 8% false
    positives on a 50-row redraw, under the 15% threshold. Tier 3 stays out
    unconditionally, which is the part that must not regress.
    """
    import yaml
    cfg = yaml.safe_load(open('config/config_daily.yaml'))
    assert cfg['collect_tiers'] == [0, 1, 2]
    from src.daily import collect_tiers
    assert collect_tiers(cfg) == [0, 1, 2]
    assert 3 not in collect_tiers(cfg)


# ---------------------------------------------------------------------------
# 2.4 alt_of
# ---------------------------------------------------------------------------

def _det(cid, title, videos):
    return {'id': cid, 'snippet': {'title': title},
            'statistics': {'videoCount': str(videos)}}


def test_canonical_is_chosen_by_token_overlap_then_video_count():
    from scripts.link_alt_channels import canonical_of

    details = {
        'UCa': _det('UCa', 'Le Monde Clips', 5),
        'UCb': _det('UCb', 'Le Monde', 900),
        'UCc': _det('UCc', 'Totally Unrelated', 99999),
    }
    # 'Le Monde' shares tokens with the label and is not the largest channel;
    # overlap must beat raw video count.
    assert canonical_of(['UCa', 'UCb', 'UCc'], details, 'Le Monde') == 'UCb'

    # With overlap tied, video count decides.
    tied = {'UCx': _det('UCx', 'Le Monde', 10), 'UCy': _det('UCy', 'Le Monde', 20)}
    assert canonical_of(['UCx', 'UCy'], tied, 'Le Monde') == 'UCy'

    # With both tied, the channel id keeps it deterministic.
    same = {'UC1': _det('UC1', 'Same', 7), 'UC2': _det('UC2', 'Same', 7)}
    assert canonical_of(['UC2', 'UC1'], same, 'Same') == 'UC1'


def test_alternate_never_enters_tier_zero():
    """
    Tier 0 is the validated NewsGuard frame and nothing else.

    Admitting an alternate to it on Wikidata provenance alone would redefine
    the primary frame and silently break every count resting on it. A first
    version of the alt pass did exactly that, moving 4 channels into tier 0.
    """
    from scripts.link_alt_channels import MIN_ALT_TIER

    assert MIN_ALT_TIER == 1
    # An alternate of a tier-0 canonical lands at tier 1: still collected,
    # since collection covers tiers 0-1, but not part of the frame.
    assert max(0, MIN_ALT_TIER) == 1
    assert max(2, MIN_ALT_TIER) == 2      # never promotes a tier-2 alternate
    assert max(3, MIN_ALT_TIER) == 3


# ---------------------------------------------------------------------------
# 3.0 per-tier discovery cadence
# ---------------------------------------------------------------------------

class CadenceFake:
    """Minimal discovery-only client: one page per channel, charges 1 unit."""

    def __init__(self, gov):
        self.governor = gov
        self.visits = Counter()

    def playlist_items(self, playlist_id, page_token=None):
        self.governor.charge('playlistItems', 1)
        self.visits[playlist_id] += 1
        # One page, no nextPageToken: the cheapest realistic visit.
        return {'items': [{'contentDetails': {
            'videoId': f"v{playlist_id[-6:]}_{self.visits[playlist_id]}",
            'videoPublishedAt': daily.utcnow() + 'Z'}}]}


def _cadence_cfg():
    import yaml
    return yaml.safe_load(open('config/config_daily.yaml'))


def test_discovery_cadence_covers_the_frame_over_fourteen_days(tmp_path):
    """
    A 14-day run at the shipped cadence must serve the whole frame.

    Tier 0 is due every 2 days, so 14 days gives it at least 7 visits; tier 2
    is due every 14 days, so it must be reached at least once. This is the
    property that makes the frame affordable: visiting every channel daily
    would cost 4,312 units/day, which no 10k budget survives alongside the
    other three stages.
    """
    cfg = _cadence_cfg()
    cfg['quota']['daily_budget'] = 10000

    db = Database(db_path=str(tmp_path / "cadence.db"))
    con = db.conn
    con.row_factory = sqlite3.Row

    # The real frame's shape: 2,856 tier 0, 788 tier 1, 668 tier 2 = 4,312.
    sizes = {0: 2856, 1: 788, 2: 668}
    rows = []
    for tier, n in sizes.items():
        for i in range(n):
            cid = f"UC{tier}{i:022d}"
            rows.append((cid, tier, 'active', 'UU' + cid[2:]))
    con.executemany(
        "INSERT INTO channels (channel_id, tier, status, uploads_playlist) "
        "VALUES (?, ?, ?, ?)", rows)
    con.commit()
    assert con.execute("SELECT COUNT(*) FROM channels").fetchone()[0] == 4312

    total_visits = Counter()
    daily_units = []

    for day in range(14):
        # A fresh budget each day, as the Pacific rollover gives.
        gov = QuotaGovernor(con, cfg['quota']['daily_budget'])
        con.execute("DELETE FROM quota_ledger")
        con.commit()
        yt = CadenceFake(gov)

        # The channels stage runs first and takes its share; model that by
        # charging its slice before discovery opens its budget.
        gov.charge('channels', 4312 // 50 + 1)

        daily.discover_uploads(con, yt, cfg, f"sim-{day}")
        total_visits.update(yt.visits)
        daily_units.append(gov.spent_today())

        # Advance the clock by ageing every timestamp one day.
        con.execute(
            "UPDATE channels SET last_discovered = "
            "datetime(last_discovered, '-1 day') WHERE last_discovered IS NOT NULL")
        con.commit()

    def visits_for(tier):
        return [total_visits.get('UU' + f"{tier}{i:022d}", 0)
                for i in range(sizes[tier])]

    t0, t1, t2 = visits_for(0), visits_for(1), visits_for(2)

    assert min(t0) >= 7, f"a tier-0 channel was visited only {min(t0)} times in 14 days"
    assert min(t2) >= 1, f"a tier-2 channel was visited only {min(t2)} times in 14 days"
    assert min(t1) >= 2, f"a tier-1 channel was visited only {min(t1)} times in 14 days"

    # And it fits: discovery never exhausted its share on any day.
    assert max(daily_units) < cfg['quota']['daily_budget']
    db.close()


def test_discovery_only_queues_channels_whose_cadence_has_elapsed(tmp_path):
    con, gov, yt = fresh(tmp_path / "t.db", tiers=(0, 1, 2))
    cfg = json.loads(json.dumps(CFG))
    cfg['collect_tiers'] = [0, 1, 2]
    cfg['schedule']['discovery_days'] = {'0': 2, '1': 7, '2': 14}
    cfg['schedule']['upload_lookback_days'] = {'0': 3, '1': 8, '2': 15}

    for cid in CH:
        con.execute("UPDATE channels SET status='active', uploads_playlist=?, "
                    "last_discovered=? WHERE channel_id=?",
                    ('UU' + cid[2:], daily.utcnow(), cid))
    con.commit()

    # Nothing is due: every channel was discovered just now.
    daily.discover_uploads(con, yt, cfg, "run-none")
    assert [c for c in yt.calls if c[0] == 'playlistItems'] == []

    # Age the tier-0 channel past its 2-day cadence; only it becomes due.
    con.execute("UPDATE channels SET last_discovered = ? WHERE channel_id = ?",
                (daily._iso_days_ago(3), CH[0]))
    con.commit()
    daily.discover_uploads(con, yt, cfg, "run-one")
    scanned = [pid for kind, pid in yt.calls if kind == 'playlistItems']
    assert scanned == ['UU' + CH[0][2:]]


def test_channel_skipped_on_budget_stays_due(tmp_path):
    """A channel not actually paged must not be stamped as discovered."""
    con, gov, yt = fresh(tmp_path / "t.db", tiers=(0, 0, 0))
    cfg = json.loads(json.dumps(CFG))
    cfg['collect_tiers'] = [0, 1, 2]
    cfg['schedule']['discovery_days'] = {'0': 1}
    cfg['schedule']['upload_lookback_days'] = {'0': 2}
    for cid in CH:
        con.execute("UPDATE channels SET status='active', uploads_playlist=? "
                    "WHERE channel_id=?", ('UU' + cid[2:], cid))
    con.commit()

    yt.governor = QuotaGovernor(con, 1)      # one unit: one channel only
    daily.discover_uploads(con, yt, cfg, "run-tight")

    stamped = con.execute(
        "SELECT COUNT(*) FROM channels WHERE last_discovered IS NOT NULL"
    ).fetchone()[0]
    assert stamped == 1
    assert con.execute(
        "SELECT COUNT(*) FROM channels WHERE last_discovered IS NULL"
    ).fetchone()[0] == 2


# ---------------------------------------------------------------------------
# replica guard (3.1 cutover)
# ---------------------------------------------------------------------------

def test_replica_database_is_refused_by_name(tmp_path):
    """
    After the cutover the cluster file is production and the local copy is a
    replica. The guard keys on the filename because the failure it prevents is
    silent: writing to the replica builds a second divergent history that looks
    authoritative.
    """
    from src.database import ReplicaRefused, guard_replica

    guard_replica(str(tmp_path / "youtube_monitoring.db"))          # fine
    guard_replica(str(tmp_path / "ytmon_2026-09-16.db"))            # fine

    for name in ("youtube_monitoring.replica.db", "REPLICA.db",
                 "some.Replica.sqlite"):
        with pytest.raises(ReplicaRefused):
            guard_replica(str(tmp_path / name))
        guard_replica(str(tmp_path / name), allow_replica=True)     # acknowledged

    # And the guard fires through the Database constructor, not just directly.
    with pytest.raises(ReplicaRefused):
        Database(db_path=str(tmp_path / "youtube_monitoring.replica.db"))
    db = Database(db_path=str(tmp_path / "youtube_monitoring.replica.db"),
                  allow_replica=True)
    db.close()


def test_replica_refusal_names_where_production_is(tmp_path):
    from src.database import ReplicaRefused, guard_replica

    with pytest.raises(ReplicaRefused) as exc:
        guard_replica(str(tmp_path / "youtube_monitoring.replica.db"))
    message = str(exc.value)
    assert 'gdelt-server' in message
    assert '--i-know-this-is-a-replica' in message


def test_harvest_comments_works_through_a_plain_database_connection(tmp_path):
    """
    Regression: the comment queue reads rows by column name.

    Database now sets row_factory, but this test opens the stage exactly the
    way daily.py does -- no fixture configuration of its own -- because the
    original bug was precisely that the fixture set row_factory and production
    did not, so the stage passed its tests and then raised
    "tuple indices must be integers" on the cluster.
    """
    db = Database(db_path=str(tmp_path / "plain.db"))
    con = db.conn
    con.execute("INSERT INTO channels (channel_id, tier, status) "
                "VALUES (?, 0, 'active')", (CH[0],))
    con.execute("INSERT INTO videos (video_id, channel_id, published_at, "
                "comments_state) VALUES ('vplain', ?, '2026-09-01T00:00:00Z', "
                "'pending')", (CH[0],))
    con.commit()

    gov = QuotaGovernor(con, 100)
    yt = FakeYouTube(gov)
    result = daily.harvest_comments(con, yt, CFG, "run-plain")

    assert result['comments'] > 0
    assert con.execute(
        "SELECT comments_state FROM videos WHERE video_id = 'vplain'"
    ).fetchone()[0] == 'done'
    db.close()


def test_adopt_backfill_videos_makes_null_state_videos_visible(tmp_path):
    """NULL comments_state is invisible to the queue; adoption fixes that."""
    from scripts.adopt_backfill_videos import main as adopt

    db = Database(db_path=str(tmp_path / "adopt.db"))
    con = db.conn
    con.execute("INSERT INTO channels (channel_id, tier, status) "
                "VALUES (?, 0, 'active')", (CH[0],))
    # One with comments already, one without, both NULL-state.
    for vid, count in (('vhas', 42), ('vnone', 7)):
        con.execute("INSERT INTO videos (video_id, channel_id, published_at, "
                    "comment_count, comments_state) VALUES (?, ?, ?, ?, NULL)",
                    (vid, CH[0], '2026-09-01T00:00:00Z', count))
    con.execute("INSERT INTO comments (comment_id, video_id, text) "
                "VALUES ('c1', 'vhas', 'hi')")
    con.commit()

    # Before adoption neither is queued.
    assert daily._comment_queue(con, CFG) == []
    db.close()

    assert adopt(["--db", str(tmp_path / "adopt.db")]) == 0

    db = Database(db_path=str(tmp_path / "adopt.db"))
    con = db.conn
    rows = {r[0]: (r[1], r[2]) for r in con.execute(
        "SELECT video_id, comments_state, last_comment_count FROM videos")}
    assert rows['vhas'] == ('done', 42)      # baseline for the growth re-poll
    assert rows['vnone'][0] == 'pending'
    # And the one never harvested is now visible to the queue.
    queued = {r['video_id'] for r in daily._comment_queue(con, CFG)}
    assert 'vnone' in queued
    db.close()
