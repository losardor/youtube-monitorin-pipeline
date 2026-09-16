"""
One definition of "now", shared by every module that stores a timestamp.

`datetime.utcnow()` is deprecated from Python 3.12 and scheduled for removal.
The replacement here produces the **same naive UTC value** with **byte-identical
serialisation**, so nothing stored changes and no migration is needed:

    datetime.utcnow()                              -> 2026-09-16T11:35:09.165226
    datetime.now(timezone.utc).replace(tzinfo=None) -> 2026-09-16T11:35:09.165226

Timestamps stay naive deliberately. Every stored value is handled **as a
string**, and an aware value serialises with a `+00:00` suffix. Ordering
survives that -- the offset is appended after the whole date and time, so for
UTC values string order still tracks time order -- but **exact equality does
not**, and several things depend on it:

  - the snapshot primary keys `(channel_id, observed_at)` and
    `(video_id, observed_at)`;
  - the migration's join of a snapshot to its record's own timestamp;
  - the `INSERT OR IGNORE` that makes re-running a backfill idempotent.

A value written naive and looked up aware does not match, and the failure is
silent: a duplicate row rather than an error. Moving to aware timestamps
therefore needs a migration of every stored value and its own gate. It is
deferred indefinitely.
"""

from datetime import datetime, timezone


def utcnow_dt() -> datetime:
    """Current UTC time as a naive datetime, matching what is stored."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utcnow() -> str:
    """Current UTC time in the exact format used throughout the database."""
    return utcnow_dt().isoformat()
