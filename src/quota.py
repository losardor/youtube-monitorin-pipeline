"""
Quota governor and per-stage budgets.

Two properties matter here:

  - Spend is recorded in the database (`quota_ledger`), not in memory, so a
    restart within the same billing day does not hand the process a fresh
    budget it does not have.
  - The ledger is keyed by the *Pacific* day, because that is the day the API
    bills against and resets on, regardless of where the job runs.

Charges are recorded only for calls the API actually served (HTTP 200); a
refused or failed call costs nothing and must not appear in the ledger.

This supersedes the `quota_cumulative` column on `collection_runs`, which was
a back-estimate reconstructed from collected row counts, not a record of
actual charges.
"""

from __future__ import annotations

import logging
from datetime import datetime

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python < 3.9
    from backports.zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

PACIFIC = ZoneInfo("America/Los_Angeles")

# Documented unit costs, YouTube Data API v3.
# Keys are endpoint names as used by QuotaGovernor.charge and YouTube._call.
COSTS = {
    "channels": 1,
    "playlistItems": 1,
    "videos": 1,
    "commentThreads": 1,
    "comments": 1,
    "captions": 50,
    "search": 100,
}

# Endpoints the daily pipeline may never call, whatever the caller passes.
# search.list at 100 units is 1% of a 10k day for one call; discovery goes
# through playlistItems on channels.uploads_playlist instead. The allow_search
# flag on the client is a separate, independent guard.
DAILY_FORBIDDEN_ENDPOINTS = frozenset({"search"})


def pacific_day(when: datetime | None = None) -> str:
    """The day the API bills against, as YYYY-MM-DD."""
    if when is None:
        when = datetime.now(PACIFIC)
    elif when.tzinfo is None:
        raise ValueError("pacific_day() needs an aware datetime")
    return when.astimezone(PACIFIC).strftime("%Y-%m-%d")


class QuotaGovernor:
    """
    Tracks spend against a daily budget, persisted per Pacific day.

    Args:
        con: sqlite3 connection (the `quota_ledger` table must exist)
        daily_budget: units available per Pacific day
        forbidden_endpoints: endpoints refused regardless of budget
    """

    def __init__(self, con, daily_budget: int, forbidden_endpoints=frozenset(),
                 charge_error_responses: bool = False):
        self.con = con
        self.daily_budget = int(daily_budget)
        self.forbidden_endpoints = frozenset(forbidden_endpoints)
        # Whether a served error response also costs budget. Off by default:
        # the ledger counts them either way, so the question can be settled
        # from data before the arithmetic is changed.
        self.charge_error_responses = bool(charge_error_responses)
        self.session_units = 0
        self.session_calls = 0
        self.session_error_calls = 0

    def spent_today(self) -> int:
        row = self.con.execute(
            "SELECT COALESCE(SUM(units), 0) FROM quota_ledger WHERE day = ?",
            (pacific_day(),),
        ).fetchone()
        return int(row[0]) if row else 0

    def remaining(self) -> int:
        return max(0, self.daily_budget - self.spent_today())

    def can_afford(self, cost: int) -> bool:
        return self.remaining() >= cost

    def is_forbidden(self, endpoint: str) -> bool:
        return endpoint in self.forbidden_endpoints

    def charge(self, endpoint: str, cost: int) -> None:
        """Record units actually spent. Call only after a served response."""
        self.con.execute(
            "INSERT INTO quota_ledger (day, endpoint, calls, units, error_calls) "
            "VALUES (?, ?, 1, ?, 0) "
            "ON CONFLICT(day, endpoint) DO UPDATE SET "
            "calls = calls + 1, units = units + excluded.units",
            (pacific_day(), endpoint, cost),
        )
        self.con.commit()
        self.session_units += cost
        self.session_calls += 1

    def charge_error(self, endpoint: str, cost: int) -> None:
        """
        Record a response the API served with a non-quota error.

        Always counted in error_calls; charged units only when
        charge_error_responses is set. Whether Google bills these is not
        documented, and 2026-09-16 could not settle it because the console sat
        below the ledger. Counting without charging lets a later day answer the
        question at no risk to the budget arithmetic.
        """
        charged = cost if self.charge_error_responses else 0
        self.con.execute(
            "INSERT INTO quota_ledger (day, endpoint, calls, units, error_calls) "
            "VALUES (?, ?, ?, ?, 1) "
            "ON CONFLICT(day, endpoint) DO UPDATE SET "
            "calls = calls + excluded.calls, "
            "units = units + excluded.units, "
            "error_calls = error_calls + 1",
            (pacific_day(), endpoint, 1 if charged else 0, charged),
        )
        self.con.commit()
        self.session_error_calls += 1
        if charged:
            self.session_units += charged
            self.session_calls += 1

    def spend_by_endpoint(self, day: str | None = None) -> dict:
        """Ledger for one day as {endpoint: {'calls': n, 'units': n}}."""
        rows = self.con.execute(
            "SELECT endpoint, calls, units, COALESCE(error_calls, 0) "
            "FROM quota_ledger WHERE day = ? ORDER BY units DESC",
            (day or pacific_day(),),
        ).fetchall()
        return {r[0]: {'calls': r[1], 'units': r[2], 'error_calls': r[3]}
                for r in rows}


class Budget:
    """
    A stage's share of the governor's remaining budget.

    Fixed at construction from what is left at that moment, so a stage cannot
    grow its allowance by running after another stage underspent, and a stage
    that stops early leaves the remainder to those that follow.
    """

    def __init__(self, governor: QuotaGovernor, share: float, floor: int = 0):
        self.gov = governor
        self.share = share
        self.start_units = governor.session_units
        self.start_calls = governor.session_calls
        self.allowance = max(floor, int(governor.remaining() * share))

    @property
    def used(self) -> int:
        """Units spent since this budget was opened."""
        return self.gov.session_units - self.start_units

    @property
    def calls(self) -> int:
        """Calls made since this budget was opened.

        Per-stage, not cumulative: ytmon logged gov.session_calls into
        run_log.calls, which is the whole session's count and makes every
        stage after the first look busier than it was.
        """
        return self.gov.session_calls - self.start_calls

    @property
    def left(self) -> int:
        return max(0, self.allowance - self.used)

    def ok(self, cost: int = 1) -> bool:
        """True if this stage can afford another call of `cost` units."""
        return self.left >= cost and self.gov.can_afford(cost)
