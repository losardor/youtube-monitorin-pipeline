"""
Error taxonomy for YouTube Data API failures.

The point of these classes is that the caller can tell apart the three things
a failed call can mean, which a bare `return None` cannot:

  - we ran out of budget                 -> QuotaExhausted  (stop, retry tomorrow)
  - this item cannot be fetched, ever    -> ItemUnavailable (record, move on)
  - something else went wrong            -> APIError        (log, decide)

Conflating the first two is the 403-swallow bug: a quotaExceeded 403 recorded
as "channel not found" marked ~752 live channels dead during the December 2025
validation runs (LOGBOOK, Runs #2 and #3d).
"""


class QuotaExhausted(RuntimeError):
    """Local budget or the API's own daily allowance is spent.

    Never means the requested item is absent. Callers must stop rather than
    record a negative result.
    """


class CommentsDisabled(RuntimeError):
    """Comments are turned off for this video. Expected, not an error condition."""


class ItemUnavailable(RuntimeError):
    """Video/channel/playlist is private, deleted, or region-blocked."""


class APIError(RuntimeError):
    """Any other non-200 response."""

    def __init__(self, status, reason, message):
        super().__init__(f"{status} {reason}: {message}")
        self.status = status
        self.reason = reason
        self.message = message


# Reason strings, grouped by what they mean for control flow.
QUOTA_REASONS = frozenset({"quotaExceeded", "dailyLimitExceeded"})
RATE_LIMIT_REASONS = frozenset({"rateLimitExceeded", "userRateLimitExceeded"})
UNAVAILABLE_REASONS = frozenset({
    "channelNotFound", "videoNotFound", "playlistNotFound",
    "commentThreadNotFound", "playlistItemsNotAccessible", "forbidden",
})
COMMENTS_DISABLED_REASONS = frozenset({"commentsDisabled"})
RETRYABLE_STATUSES = frozenset({500, 502, 503, 504})
