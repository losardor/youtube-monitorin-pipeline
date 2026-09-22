# YouTube Monitoring Pipeline - Logbook

## Current Status (as of 2026-09-22)

**Current phase:** Phase 3 running. Six cron runs on six consecutive days (09-17 to 09-22). **Gate 3 at 5 of 6**; (f) sizing re-derivation opens with the seventh run on 09-23. Post-Gate-3 follow-ups deployed as `b177bf3` (tag `ytmon-gate3-followups`).

- **Production database:** `gdelt-server:/data/ytmon/youtube_monitoring.db` (cutover 2026-09-16T10:47:44Z) — 2,856 tier 0, 788 tier 1, 668 tier 2, 1,724 tier 3. `collect_tiers: [0, 1, 2]`. The Mac copy is `data/youtube_monitoring.replica.db` and is refused by the replica guard.
- **Gate 2:** tier 1 0/25 = 0%; tier 2 4/50 = 8% on the redraw under rule (a), 4/63 = 6.3% pooled. Both pass.
- **Quota spent on tiering:** 2,505 units across 2026-09-15/16. All API responses archived and backed up to `gdelt-server:/data/ytmon/backups/`; everything downstream recomputes free.

- **Validated URLs:** 3,307 / 3,307 (100%)
- **Confirmed channels:** 2,867 (86.7% success rate after Run #3d recovery pass)
- **Deferred:** 286 expensive bug-contaminated entries (`/c/`, `/user/`) — re-validation blocked on 1M quota approval
- **Main collection:** blocked on 1M quota approval (request submitted 2026-04-20, response pending)
- **403-swallow bug:** **FIXED 2026-09-15** in phase 1.2 — was present in five methods, not one. See the 2026-09-15 entry.
- **Validated frame location:** `data/validation/validation_progress.json` (2,867 successes, 2,856 distinct ids). **Loaded into the production database 2026-09-16** as tier 0; see the phase 2 entry.
- **DB channel mismatch (31 vs 73):** investigated in Task 1 on 2026-04-21 — resolution: "73" was never unique channels; it matched the sum of `channels_processed` attempts across completed Nov 19 runs. See the 2026-04-21 resolution entry below.

---

## 2024-12-11: URL Cleanup and Validation

### URL Fixes Applied to sources.csv
- **244** comma-separated URLs fixed (kept first URL)
- **10** URL-encoded URLs decoded (e.g., `%C3%A9` → `é`)
- **188** URLs cleaned (removed `/videos`, `/featured`, query params)
- Backup created: `data/sources_backup_20251211_171901.csv`
- Verification: 0 remaining comma-separated, 0 remaining URL-encoded

### URL Format Distribution (after cleanup)
| Format | Count | Quota Cost |
|--------|-------|------------|
| `/channel/UC...` | 4,536 | 1 unit each |
| `/@handle` | 375 | 1 unit each |
| `/c/customname` | 829 | 1-101 units (search fallback risk) |
| `/user/username` | 612 | 1-101 units (search fallback risk) |
| Other | 6 | varies |
| **Total** | **6,358** | |

### Validation Run #1 (Dec 11, ~16:00)
- **URLs validated**: 1,343 / 3,310 unique
- **Quota used**: 10,001 units (exhausted daily quota)
- **Issue**: 93 URLs triggered search fallback (100 units each) = ~9,300 units
- **Results**:
  - Success: 529 (39.4% - but many failures were quota-related)
  - Failed: 814 (60.6% - includes false positives from quota exhaustion)

### Validation Run #2 (Dec 15, fresh quota)
- **Starting point**: Resuming from 1,343 validated
- **URLs validated this run**: 1,000
- **Success rate**: 77.2% (772 success, 228 failed)
- **Quota used**: 10,054 units (exhausted daily quota)
- **Avg quota per URL**: ~10 units
- **Status**: Complete

### Cumulative Progress After Run #2
- **Total validated**: 2,343 / 3,307 (70.8%)
- **Remaining**: 964 URLs (need Run #3 tomorrow)
- **Note**: Run #1 success rate was artificially low due to quota exhaustion marking channels as "failed"

### Validation Run #3a (2026-04-20, cheap batch only)
- **Split strategy**: Pre-filtered `sources.csv` into cheap (`/channel/UC...` + `/@handle`) and risky (`/c/`, `/user/`, bare names) buckets. Under the confirmed 10K/day ceiling, running the 1,013 remaining unfiltered risked burning quota on the ~137 fallback-risk URLs before clearing the cheap bulk.
- **Starting point**: Resuming from 2,294 validated (post-reconcile state)
- **URLs validated this run**: 876 (all cheap)
- **Success rate**: 96.2% (843 success, 33 failed)
- **Quota used**: 1,399 units (14% of 10K ceiling — massive headroom)
- **Avg quota per URL**: 1.60 units
- **Failures**: All 33 are `"Channel not found (deleted/private/suspended)"` — same pattern as Runs #1–#2, genuine dead channels. **Zero `cost=0` failures** → no 403-swallow contamination.
- **Status**: Complete. 2,294 → 3,170 validated. 137 risky URLs remain.

### Validation Run #3b (2026-04-21, risky batch partial — cap 95)
- **Split strategy**: Still on 10K/day ceiling (1M request pending). Capped at `--limit 95` to keep worst case (95 × 100 = 9,500) under 10K.
- **URLs validated this run**: 95
- **Success rate**: 98.9% (94 success, 1 failed)
- **Quota used**: 4,538 units (45% of 10K ceiling)
- **Avg quota per URL**: 47.77 units
- **Cost distribution**: 51 URLs resolved at 1 unit (handle/username direct hit), 44 URLs hit search fallback at ≥100 units — 46% fallback rate, consistent with Dec 11/15 profile.
- **Failures**: 1 `"Channel not found (deleted/private/suspended)"`. Zero `cost=0` failures → no 403-swallow contamination.
- **Status**: Partial. 3,170 → 3,265 validated. 42 risky URLs remain (all `/c/` or `/user/` that were beyond the --limit 95 cap).

### Validation Run #3c (2026-04-21, closing pass)
- **URLs validated this run**: 42
- **Success rate**: 95.2% (40 success, 2 failed)
- **Quota used**: 2,464 units (avg 58.67/URL — 24 of 42 hit 100-unit search fallback, 57% rate)
- **Failures**: Both `"Channel not found"`. Zero `cost=0` failures.
- **Status**: Complete. 3,265 → **3,307 validated (100%)**.

### Day 2026-04-21 combined (Runs #3b + #3c)
- **Total URLs validated today**: 137
- **Total quota used today**: 7,002 units (70% of 10K ceiling)
- **Remaining quota today**: ~2,998 units (unused)

---

## Validation Phase — CLOSED (2026-04-21)

| | Count |
|---|---|
| Total unique URLs in `sources.csv` | 3,307 |
| **Validated** | **3,307 (100%)** |
| Pending | 0 |
| Cumulative success | 2,252 (68.1%) |
| Cumulative failed | 1,055 (31.9%) |

### Contamination caveat
~137 entries from Dec 15 Run #2's tail are recorded as `"Channel not found"` with `cost=0` — these are the 403-swallow artifacts (see Known bugs). The true failed count excluding that contamination is ~918 (27.8%). The 137 contaminated entries should be re-validated after the 1M quota increase lands (or on any day with spare budget). Filter: `cost=0 AND success=false AND validated_at LIKE '2025-12-15T15:%'`.

### Runs summary
| Run | Date | URLs | Success | Quota | Notes |
|---|---|---|---|---|---|
| #1 | 2025-12-11 | 1,343 | 529 | 10,001 | Quota exhausted mid-run. |
| #2 | 2025-12-15 | 1,050 | 772 | 10,054 | Tail ~137 URLs contaminated by 403-swallow. |
| corrected | 2025-12-23 | 70 | 69 | ~69 | URL-correction re-validation (separate script). |
| #3a | 2026-04-20 | 876 | 843 | 1,399 | Cheap batch (`/channel/UC` + `/@`). 96.2% success. |
| #3b | 2026-04-21 | 95 | 94 | 4,538 | Risky batch partial (cap 95). 98.9% success. |
| #3c | 2026-04-21 | 42 | 40 | 2,464 | Risky closing pass. 95.2% success. |

### Next phase
- **Main collection** (videos + comments + captions via `collect.py`) can now proceed against the **2,867 validated successful channels** (updated after 2026-04-21 bug-recovery pass).
- **Pre-flight before collection:**
  - ~~Re-validate the 137 Dec 15 contaminated entries once quota allows~~ → **Cheap portion done 2026-04-21 (Run #3d, see below): 615 of 647 recovered.** 286 expensive (`/c/`, `/user/`) entries still contaminated; blocked on 1M quota approval.
  - ~~Reconcile the 31-vs-73 DB channel discrepancy~~ → **Resolved 2026-04-21, see below.**
  - **Fix `get_channel_info` 403-swallow bug** before running `collect.py` — otherwise main collection risks the same contamination on any quota-exhaustion day.
  - Confirm 1M quota approval status before kicking a multi-day `collect.py` run.

---

## 2026-04-21: Resolved 31-vs-73 DB channel mismatch

**The "73" was never unique channels** — it was the sum of `channels_processed` across the 4 completed Nov 19 test runs (3 + 20 + 50 + 3 = **76**), likely rounded/misremembered as 73 in earlier LOGBOOK notes. That column counts *attempts*, including duplicates (same channel referenced from multiple source rows) and possibly re-queries. The `channels` table PRIMARY KEY on `channel_id` collapses these to **31 unique channels** actually stored.

### Evidence

| Check | Result |
|---|---|
| `channels` table row count | 31 |
| Sum `channels_processed` (completed runs) | 76 |
| Distinct `channel_id` in `videos` | 30 |
| Orphan videos (channel_id not in channels) | 0 |
| DB channels also in `validation_progress.json` | 29 / 31 |
| DB channels NOT in validation results | 2 (WDR Doku `UCUuab1dctZzN5ZmRmQnTzkg`, parismatch `UCaBU6qj0GRLDnykr44r26Tg`) |

The 2 DB-only channels were collected Nov 19 from `sources.csv` URLs that — after the Dec 23 URL cleanup pass — either resolve differently or fail to resolve. Both are legit YouTube IDs with content. Non-critical: the Nov 19 data is intact, just not linked to current validation entries.

### Verdict
**(a) LOGBOOK "73" was aspirational/wrong.** No channels were dropped. No orphans. No action required — the DB is consistent with what actually completed on Nov 19.

---

## 2026-04-21: Validation Run #3d — Bug-contaminated recovery (cheap bucket)

Post-validation bug-recovery pass. Targets: entries in `validation_progress.json` where the 403-swallow bug in `get_channel_info` silently converted quota-exceeded errors into `quota_cost=0 + success=False + error="Channel not found"`. Scope limited to cheap URL types (`/channel/UC`, `/@handle`) on Dec 11 and Dec 15 (the two days where the main validator exhausted quota mid-run). Expensive buckets (`/c/`, `/user/`) deferred pending 1M quota approval.

### Tooling
New script: `scripts/revalidate_contaminated.py`. Key properties:
- **Bypasses the buggy `get_channel_info`** — calls `YouTubeAPIClient._make_request` directly, which correctly re-raises HttpError 403 on quota exhaustion.
- **Defense-in-depth**: aborts if three consecutive `(quota_cost=0, success=False)` responses occur mid-run, which would indicate the underlying client still has a swallow path.
- **Audit trail**: every updated entry retains its pre-revalidation state under a `revalidation_history` array, tagged with `superseded_by`.
- **Atomic writes**: tmp + fsync + rename, every 25 entries. Backup file created before any mutation.

### Run in two parts (first attempt hit a script bug)

**Part 1:** processed 478 entries, then crashed on a truncated channel ID (`UCmgnsaQIK1IR808Ebde-ss`, 23 chars) that tripped an over-strict length assertion in the script. 475 entries durably written via checkpoint-every-25; entries 476–478 lost. Script patched to pass unknown IDs through to the API (which returns `items=[]` at 1 unit) rather than crashing.

**Part 2:** re-ran the remaining 172 cleanly.

### Combined results

| Metric | Value |
|---|---|
| Target selected | 647 (456 Dec 11 + 191 Dec 15) |
| Attempted | 647 |
| **Recovered** (previously "not found", now success=True) | **615** |
| Still failed (confirmed deleted/private/suspended) | 32 |
| Quota used | **647 units** (avg 1.00/URL, matches estimate exactly) |
| Elapsed | ~5 min total |

95.1% of contaminated cheap entries were actually real channels — they were victims of the bug, not genuine failures.

### Spot-check (5 random recovered entries, seed=42)
All passed:
- Channel IDs all proper UC + 24 chars
- Channel titles match source brand (e.g., `Braunschweiger Zeitung` ↔ `Braunschweiger-Zeitung.de`, `The Irish Post` ↔ `The Irish Post`)
- Reasonable subscriber / video counts
- `revalidation_history` preserved with `superseded_by` tag

### Cumulative validation (after Run #3d)

| Metric | Pre-#3d | Post-#3d |
|---|---|---|
| Validated | 3,307 | 3,307 |
| Success | 2,252 (68.1%) | **2,867 (86.7%)** |
| Failed | 1,055 (31.9%) | **440 (13.3%)** |

### Still-contaminated (deferred)
286 entries remain with the bug signature — all `/c/` (161) and `/user/` (125) URL forms. Worst-case re-validation cost: 28,600 units → over 10K ceiling. Blocked until the 1M quota approval lands.

---

## 2026-09-15: Phase 1 — monitoring core ported (Gate 1 passed)

Branch `feat/daily-monitor` off `production`, per `docs/briefs/CC_brief_ytmon_merge.md`.
Ports the ytmon reference implementation in `external/ytmon/` into the pipeline:
snapshot tables, a quota governor with a real error taxonomy, the four daily
stages, and an advisory lock shared with the backfill.

### Gate 1 result

**`pytest -q`: 115 passed, 6 warnings in 9.98s.** (29 new in `tests/test_daily.py`.)

**`view_data.py --stats`, before vs after `scripts/migrate_snapshots.py` on a copy of
`data/youtube_monitoring.db`: identical, zero diff.**

```
Channels:          31            Channels:          31
Videos:            5,255         Videos:            5,255
Comments:          693,204       Comments:          693,204
Total Views:       594,305,900   Total Views:       594,305,900
Avg Views/Video:   113,244       Avg Views/Video:   113,244
Unique Commenters: 271,863       Unique Commenters: 271,863
```

**`daily.py status` after migration** (the second gate check):

```
channel_snapshots            31 rows over 2 day(s)
video_snapshots           5,255 rows over 2 day(s)
```

Second migration run inserts 0 and 0; both counts unchanged. The migration was
run only on copies under the session scratchpad. The original
`data/youtube_monitoring.db` has md5 `795bb9716410458888ff39355bde04a9` before
and after — never opened for writing.

### What changed

| Sub-section | Commit | Substance |
|---|---|---|
| 1.1 | `eab26e1` | `channel_snapshots`, `video_snapshots`, `quota_ledger`, `run_log`; 7 new `channels` columns and 5 new `videos` columns via PRAGMA-guarded ALTER; `scripts/migrate_snapshots.py` |
| 1.2 | `bfbeda4` | `src/quota.py`, `src/errors.py`, `_call` chokepoint, 403-swallow fix, four scripts deleted |
| — | `c957f1d` | Liveness checks moved off `search.list` |
| 1.3 | `07cd619` | `src/daily.py`, `daily.py` CLI, `config/config_daily.yaml`, `src/lock.py` |
| 1.4 | `55aa4ff` | `collect.py` takes the lock; `DEPLOYMENT.md` crontab rewritten |
| 1.5 | `2162a18` | `tests/test_daily.py`, two pre-existing test failures fixed, coverage omit |

### Where the 2,867 validated channels actually live

Asked before the gate, because phase 2 defines tier 0 as that set.

**They are in `data/validation/validation_progress.json`, not in any database.**
That file holds `{"validated": [...3307 urls...], "results": [...3307 objects...]}`,
of which **2,867 have `success: true`**, resolving to **2,856 distinct `channel_id`
values** (11 channels are referenced by two source rows each).

`data/youtube_monitoring.db` holds only **31** channels — the Nov 19 2025 test runs.
Overlap between the two: **29**. The 2 DB-only channels are the WDR Doku /
parismatch pair already documented in the 2026-04-21 entry. `data/validation/
validation_results.csv` is a stale pre-#3d export (2,252 successes) and must not
be used as the frame.

**Consequence for deployment:** the production database does not yet contain the
validated frame. Before the daily run is useful, the 2,856 channel ids have to be
loaded into `channels` (tier 0), and `scripts/migrate_snapshots.py` must be run
against whichever file becomes the live database — running it against today's
31-channel file backfills only those 31. Loading the frame is not in phase 1's
scope; it is a prerequisite for phase 3 and overlaps phase 2.1.

### Note on `quota_cumulative` — do not read it as measured

The four deleted scripts (`check_quota_bug.py`, `migrate_quota_fix.py`,
`test_quota_fix.py`, `verify_quota.py`) were chasing **a different bug** from the
403 swallow: arithmetic under-reporting of quota in `collection_runs.quota_used`.

That work is **superseded by `quota_ledger`**, which records actual charges per
endpoint per Pacific billing day, written only on HTTP 200.

**The `quota_cumulative` values on historical `collection_runs` rows are a
back-estimate**, not a measurement. `migrate_quota_fix.py` reconstructed them from
collected row counts as `max(reported, estimated)` where `estimated = channels*2 +
(videos//50)*2 + (comments//100)`. They are left in place rather than rewritten,
but nobody should later read them as observed spend. Actual spend from here on is
`quota_ledger` only.

### Secrets check

`config/config.yaml` and `config/config_comprehensive.yaml` both contain live API
keys. Both are **untracked and gitignored** (`.gitignore:52-53`), and neither
appears anywhere in git history (`git log --all -- <path>` is empty). A scan of the
entire tracked tree for `AIza`-prefixed keys returns nothing. **No key rotation is
needed.** `config/config_daily.yaml`, added this phase, carries no key at all:
`daily.py` requires `YOUTUBE_API_KEY` from the environment.

### Commit boundaries for data provenance (added 2026-09-15)

Two commits on `feat/daily-monitor` are provenance boundaries. Any dataset built
from code before them carries the corresponding defect; anything built after does
not. Both are recorded here so a future reader can date a database file against
them rather than guess.

**`bfbeda4` (1.2) — the truncation boundary.** Before this commit, the client
could silently truncate video and comment collection on quota exhaustion and
record the result as complete:

- `get_channel_videos` and `get_video_details` caught the quota failure and
  returned the *partial* list they had accumulated, so the caller recorded the
  channel as fully collected when it was not.
- `get_video_comments` treated any HTTP 403 as `commentsDisabled`, `quotaExceeded`
  included, so a quota-exhausted video was written as having comments turned off.

A channel or video collected before `bfbeda4` on a day that hit the quota ceiling
may therefore hold an undercount presented as a complete count, and a video may be
marked comments-disabled when it is not. **Every production backfill from now on
runs on code after `bfbeda4`.** The 31 channels and 5,255 videos already in the
database were collected 2025-11-19, before the boundary; the Nov 19 runs did not
report quota exhaustion (185, 274, 723 units against a 10,000 ceiling), so they are
very unlikely to be affected, but they are on the wrong side of it.

**`eab26e1` (1.1) — the column-preservation boundary.** Before this commit,
`INSERT OR REPLACE` in `insert_channel` and `insert_video` deleted the old row and
did not restore the daily-pipeline columns, so any re-insert reset `tier` to its
default, dropped `uploads_playlist`, and discarded `comment_cursor`,
`comment_pages_fetched` and `comments_state`. In practice this means a backfill
re-touching a channel would have silently undone phase 2's tiering and restarted
comment harvesting for that video from page one. No data was collected between the
columns being added and the preservation being added -- both are in the same
commit -- so this boundary is a statement about the pattern, not about existing
rows.

### Bugs found and fixed while porting

1. **The 403 swallow was in five places, not one.** `get_channel_info` and
   `get_channel_by_username` are the two named in the brief. Also fixed:
   `get_channel_videos` and `get_video_details` returned a *truncated list* on
   quota failure, so the caller would record a partially collected channel as
   complete; and `get_video_comments` treated **any** 403 as comments-disabled,
   `quotaExceeded` included. The video/comment paths would have silently lost data
   on any quota-exhaustion day of a `collect.py` run.

2. **`INSERT OR REPLACE` would have wiped the new columns.** It deletes the old row,
   so a backfill re-inserting a channel would have reset `tier` to 0 and dropped
   `uploads_playlist`, and re-inserting a video would have discarded
   `comment_cursor`, restarting comment harvesting from page one. Both
   `insert_channel` and `insert_video` now carry those columns across explicitly.
   Pinned by `test_insert_replace_preserves_daily_pipeline_columns`.

3. **`src/lock.py` double-closed its file descriptor** on the contended path: the
   error branch closed the fd and the `finally` closed it again, and the resulting
   `EBADF` masked `LockUnavailable` with a misleading "Bad file descriptor". Found
   by writing the contention test the brief asked for. Acquisition is now separate
   from the held region.

4. **`channels.first_collected_at` was in the DDL but never written** — NULL on all
   31 rows, because `insert_channel` only ever set `last_updated_at`. Now populated,
   and the migration reads `COALESCE(first_collected_at, last_updated_at)`.

### Carried-over details

- `run_log.calls` is **per stage**, not the session total. ytmon logged
  `gov.session_calls` into every stage row, which is cumulative and overstates
  every stage after the first. `Budget.calls` snapshots the counter at stage start.
- Comment rows map to the existing `comments` schema (`author_name`, `text`). The
  ytmon salted-hash privacy indirection is **not** ported: there is no such column
  and 693,204 existing rows already store display names. Worth a separate decision
  if the co-commenter layer wants pseudonymisation.
- 61 videos with comments disabled keep `comment_count` NULL in both `videos` and
  `video_snapshots`; `hidden_subscribers` is NULL on all 31 backfilled channel rows,
  as no source column exists. Neither is coerced to 0.
- `search.list` is now refused twice over on the daily path: `allow_search=False` on
  the client, and the governor bans the `search` endpoint outright. The remaining
  legitimate call sites are `src/resolve_youtube.py` (the anchor-pipeline matcher,
  out of scope) and the `/c/` + `/user/` URL-resolution fallback in
  `get_channel_by_username`, which is backfill-only.
- The three liveness checks (`test_api_quick.py`, `test_api_simple.py`,
  `test_comprehensive.py`) each spent **100 units per invocation** on a `search.list`
  call to ask whether the key was valid. Now `channels.list(forHandle='@YouTube')`,
  1 unit. Verified against the live API.

### Not verifiable locally

`flock(1)` does not exist on macOS, so the shell-side half of the lock contention
(the cron wrapper's `flock -n` against the Python `fcntl.flock`) **could not be
tested on this machine** — `command -v flock` returns nothing. The Python-to-Python
contention is tested and passes (refused in 23 ms). Both take the same kernel lock
on the same inode, so they will contend on Linux, but **this needs confirming on
`infosphereVM` as part of Gate 3**, which already calls for a forced collision.

### Open for phase 2 / 3

- Load the 2,856 validated channel ids into `channels` as tier 0.
- `channels.uploads_playlist` is empty until the first `resolve_channels` pass
  (~58 units for the whole validated frame, 1 unit per 50 channels). That pass
  writes the *next* observation, not the first: the validation-phase statistics
  (Dec 2025 - Apr 2026) are loaded into `channel_snapshots` in phase 2.0, so
  the series already has an earlier point for 2,845 of the 2,856 tier-0
  channels.
- `deploy/run_daily.sh`, `deploy/healthcheck.sh`, `deploy/backup.sh` and
  `docs/operations/ytmon_daily_run.md` are phase 3; `DEPLOYMENT.md` already
  references the 09:17 slot they will implement.
- `SERVER_MIGRATION_GUIDE.md` still needs its superseded-by notice (phase 3).

---

## 2026-09-22: Cluster status check, day 6 of the daily series; Gate 3 at 5 of 6

Read-only inspection of infosphereVM by CC; full report in `docs/reports/cluster_status_2026-09-22.md`. Deployed `deploy/VERSION` was 2f34fbc, the `production` tip (`feat/post-gate3` merged as b941df2, three LOGBOOK-only commits after it); the 09-17 and 09-18 runs were on 93debfa, the 09-19 to 09-22 runs on the current build.

### Series health
Six cron runs on six consecutive days (09-17 to 09-22), all four stages non-zero, no zero-unit stage. Units per day 6,255 to 6,551 of the 9,000 budget. Comments hit their share ceiling on every run, refresh_videos on 09-19, 09-21 and 09-22. run.jsonl agrees with run_log on every figure. The 09-18 ledger exceeds run_log by exactly 32 units: the `recheck_unresolved.py` pass, ledger-charged, belonging to no run.

State: comments 83,126 pending / 21,047 done / 4,548 expired. refresh_videos queue 39,467 (09-19) to 108,743 (09-22), 58,355 cleared on 09-22. Tier 0 discovery settled into alternating cohorts of 1,683 and 1,137 channels after the 09-19 sweep could not finish 2,820 due channels inside its share; max channel age 1.08 days, cadence holding. The predicted idle discovery days never occurred, so the "no alert on an idle stage" half of that healthcheck rule is still unexercised.

Storage: live DB +62 MB/day, `/data/ytmon` +298 MB/day, NAS +164 MB/day. Backups present every night since 09-17, NAS pruning to 3 dailies correct.

### Gate 3: 5 of 6
(Item (e) was recorded as passing on a misattributed console figure; corrected below. It passes, on two days rather than one.)
- (a) three consecutive clean cron runs: verified, 09-19/20/21.
- (b) forced flock collision, (c) backup restore with integrity_check, (d) cluster-venv pytest (150 passed, 1 skipped): verified 09-18.
- (e) ledger vs console: **passed on 2026-09-16 and 2026-09-22.**

  **Correction (2026-09-22, after the entry was first written).** The 6,348 figure recorded here as 09-16's console reading is not 09-16's: it was read on Pacific day 09-22 and is that day's usage. 09-16's console figure is 6,666, supplied on 09-16. The original line compared 6,348 against 09-16's ledger and drew the wrong conclusion from the difference.

  Which figure the console should match depends on what the build was charging that day. `a4c5d37` (charge served errors) was committed 2026-09-16 13:53 CEST, *after* the last 09-16 run started at 13:09 CEST, so the 09-16 runs charged HTTP 200 only; every run from 09-17 to 09-22 ran a build containing it and charged served errors.

  | day | regime | console | 200-only | errors-charged | verdict |
  |---|---|---|---|---|---|
  | 09-16 | 200-only | 6,666 | 6,394 (4.25%) | 6,606 (**0.91%**) | errors-charged |
  | 09-22 | charged | 6,348 | 6,264 (1.34%) | 6,348 (**0.00%**) | errors-charged |

  (09-16 figures are the daily project only, i.e. the 7,117-unit ledger less the 723 units spent pre-cutover on the old project.)

  Both days match the errors-charged figure inside 1% and reject the 200-only figure outside it. **YouTube does bill a response it served with a non-quota error.** Console figures for 09-20 and 09-21 were not supplied (placeholders in the request); 09-21 would be the sharper test of the two, its two hypotheses being 3.13% apart against 09-20's 1.02%.

  Served errors were 403 `commentsDisabled` in every case bar one 400 `processingFailure` on 09-22: 212 / 41 / 92 / 98 / 63 / 199 / 84 across 09-16 to 09-22.
- (f) sizing re-derivation after seven runs: open, seventh run due 09-23.

### Defects found and fixed in this entry's branch (`fix/gate3-followups`)
1. `resolve_channels` skipped whole days: due test compared `last_checked` against run start minus exactly one day, with `last_checked` written at stage start, so cron jitter decided staleness. Channel snapshots missing for 09-19 and 09-22. Fixed with the Pacific-date comparison discovery already uses (ee6a1d3).
2. `backup.sh` output was discarded (no redirect, no MTA). Now logs to `logs/backup.log`, prints `integrity_check: <result>`, exits non-zero on anything other than ok; healthcheck alerts on a stale or failed verdict.
3. `daily.py status` required an API key it never used. Client construction is now lazy.
4. Ledger counted HTTP 200 only. `quota_ledger.error_calls` now counts non-quota error responses per endpoint and day; `quota.charge_error_responses` charges them when set; `daily.py status` prints units, calls, error_calls and their sum for the last 7 Pacific days for console comparison.

   **`821d5e6` reversed `a4c5d37` on a misread console figure.** `a4c5d37` had charged served errors unconditionally; `821d5e6` put that behind a flag defaulting to false, on the reasoning that the console sat *below* the ledger on 09-16 and so could not support charging. That reasoning rested on comparing 09-22's console figure against 09-16's ledger. With each day's figure matched to its own ledger and its own charging regime, both available days say the opposite: served errors are billed.

   **`quota.charge_error_responses` is therefore `true`, effective Pacific day 2026-09-23** (set 2026-09-22, before that day's 09:18 Rome run). This restores `a4c5d37`'s arithmetic, but deliberately and with `error_calls` recorded separately, so the question stays answerable from the data rather than from an assumption. Flipping it back is a LOGBOOK event carrying its Pacific day.
5. One 400 processingFailure on commentThreads (61inYxp3n2A) left the video pending; retry on a later run confirmed as-is. `harvest_comments` sets the state back to `pending` and `_comment_queue` admits any pending video without consulting a failure count, so no retry counter was added; the live row still reads `pending` with `comment_pages_fetched = 0`. A second test pins the bound that makes a counter unnecessary: a permanently failing video is retired by the expiry sweep when it ages out of its tier's tracking window.

### Observations
- refresh_videos is unbounded: every discovered video re-enters the refresh queue and the stage shares 20% of the budget with resolve. The 09-23 sizing step decides a refresh policy (candidate: daily inside the 30-day window, weekly beyond) rather than a share.
- Tier-0 coverage reads 1.0 because no tier-0 video has aged out of the 30-day window yet (expired = 0); the figure becomes informative around 2026-10-16.

Deployed to infosphereVM as deploy/VERSION b177bf3, 2026-09-22 12:18 CEST, before the 09-23 run. Cluster pytest: 167 passed, 1 skipped.

---

## 2026-09-18: Gate 3 interim + post-gate-3 changes deployed

### Gate 3 — RESET to 09-19/20/21, counting from `b98418e`

**The run counter restarts.** Runs 09-17 and 09-18 executed `93debfa`; the
changes below alter the behaviour of every stage — discovery cadence, comment
queue ordering and expiry, the status a failing channel receives, and what the
healthcheck alerts on. Three consecutive clean runs are evidence about *one*
build, so runs on the superseded code cannot be counted towards the deployed
one. The qualifying runs are **2026-09-19, 09-20 and 09-21**, all on
`b98418e` or its merge into `production`.

The two earlier runs are not discarded as evidence — they are what surfaced the
four defects, and their ledger and row-growth reconciliation still stands. They
simply attest to a build that is no longer deployed.

**Gate criterion, ruled 2026-09-18, before any qualifying run:**

> non-zero units in every stage **that had due work**, and no healthcheck
> alert on a stage that had none.

Recorded ahead of the runs deliberately. The literal reading — "non-zero units
in every stage" — would fail 09-20 and 09-21, where `discover_uploads`
correctly spends nothing because the corrected cadence leaves nothing due.
Settling that after seeing the results would be indistinguishable from moving
the goalposts, so it is settled here first. The idle days are the intended
case, and their silence in the healthcheck is part of the evidence.

| Criterion | Status |
|---|---|
| Three consecutive clean cron runs, non-zero units in every stage **with due work**, no alert on an idle one | **0 of 3 on `b98418e`** — 09-19, 09-20, 09-21 pending (09-17 ✔ and 09-18 ✔ were on `93debfa`) |
| Forced collision → `flock` exit | **PASS** — exit 1, 0s, ledger unchanged |
| Healthcheck email on that collision | **FAIL** — see below |
| Backup restore + `integrity_check` | **PASS** — `ok`, 0 foreign-key violations |
| `pytest -q` in the cluster venv | **PASS** — 144 passed, 1 skipped |
| Ledger vs console within 1% | **awaiting the 09-16 console figure** |

The collision test exposed a genuine gap: the deployed healthcheck's staleness
rule is "no run finished in 36 hours", and one skipped run sits well inside
that, so a collision is silent until two consecutive days are lost. Fixed
below.

### Status after two cron mornings

```
runs        09-17  6,384 units, 4 stages, 28m22s
            09-18  5,714 units, 4 stages, 14m28s
ledger      09-16 7,117 · 09-17 6,384 · 09-18 5,714   (budget 9,000)
rows        videos 5,255 -> 67,082 · comments 693,204 -> 868,720
            channel_snapshots 5,737 -> 11,537 · video_snapshots 5,255 -> 99,062
```

`run_log` items reconcile **exactly** against row growth on all four tables,
which is the strongest integrity signal available without re-querying the API.

**Comments hit their share ceiling on every run**; discovery hit it on 09-16
and 09-17. No day approached the 9,000 budget — the shares bind first, leaving
2,616 and 3,286 units unspent.

### Four problems found and fixed (`ee6a1d3`, branch `feat/post-gate3`)

**1. The comment queue could never drain its tail.** Ordering put every
`pending` video ahead of every re-poll, then sorted by date, so 52,621 newly
discovered videos permanently outranked the 4,305 adopted from the backfill.
Three runs in, not one of them had been harvested.

Two new states make this countable rather than silent. `expired`: a pending
video past its tier's `comment_tracking_days`, retired at the start of
`harvest_comments` and counted in `run_log.note` — it could never be reached,
so leaving it `pending` overstated the backlog forever. `deferred`: the 4,305
adopted videos, parked explicitly. They claimed only **6,532 comments between
them**, so almost nothing is given up.

Queue order is now `tier ASC, published_at DESC`. Tier-0
`max_comment_pages_per_video` 50 → 10: at 50 one busy video could take a
twentieth of the day's comment share while videos behind it expired.

**Coverage is the metric from now on** — of the videos in a tier's window that
reached a terminal state, the share harvested rather than expired. Baseline
now, before the first sweep:

```
tier 0, 30-day window:  8,808 done · 0 expired · 21,032 pending
                        coverage 100% of settled, but 70% not yet settled
tomorrow's sweep will expire 3,010 tier-2 videos (7-day window)
```

That 21,032 pending is the real question the metric exists to answer, and it
resolves over the next few runs as those videos either get harvested or age
out.

**2. Tier 0 was running at a 2.85-day cadence, not 2.** "Older than 2 days"
evaluated at a fixed 07:18 run means a channel discovered at 10:00 comes due at
10:00 two days later — *after* that morning's run — so it waits another day.
Observed directly: 2,704 tier-0 channels were last discovered on 09-16 and were
not visited on either 09-17 or 09-18. The cadence now compares Pacific dates,
so "every 2 days" means what it says whatever the hour. Tested on the
2026-09-16 10:00 case.

**3. Healthcheck.** NAS growth now requires **>25% AND >1 GB**: the ratio alone
fired every day while the share filled from one backup to two (+121% but only
+0.2 GB), and an alert that cries wolf daily is one nobody reads. New alert for
**any stage that had work due and spent 0 units** — the shape of a silent
failure, and the gap the collision test exposed. Stages now write a parseable
`due=` token so an idle stage is distinguishable from a failed one. `--dry-run`
prints without sending. NAS retention 14 → 3 daily.

**4. `unresolved` conflated two different failures**, and the pair oscillated.
A channel whose uploads playlist refused was marked `unresolved` by discovery;
`resolve_channels` then flipped it back to `active` on its next pass, discovery
demoted it again, and so on, a unit at a time, forever. New status
`uploads_unavailable`, which `resolve_channels` does not resurrect.

The 41 existing rows re-checked for **32 units**:

| Before | After | Meaning |
|---|---|---|
| 41 unresolved | **31 uploads_unavailable** | channel resolves; `playlistNotFound` on its uploads playlist |
| | **10 unresolved** | `channels.list` does not return the id — genuinely gone |

All 31 failed identically with `playlistNotFound`, which is why the split is
clean.

### Operational note

A read-only status check earlier today ran `healthcheck.py` to see what it
reported, which **also sends** on failure — it posted a duplicate `[ytmon]`
alert at 12:51:58 UTC alongside the genuine cron one at 10:46:01. Same
`thread_key`, so it threaded rather than arriving separately. The new
`--dry-run` flag exists so that cannot recur.

### Quota

32 units (unresolved re-check). Everything else was database-only.
Day total 2026-09-18: 5,746.

### Open

- Gate 3 on `b98418e`: runs 09-19, 09-20 and 09-21, plus the 09-16 console
  figure. Tag `ytmon-gate3-closed` only after the 09-21 run.
- First expiry sweep and first real coverage figure land with the 09-19 run.
- **09-20 and 09-21 are expected to be idle discovery days.** After the 09-19
  tier-0 sweep nothing is due until 09-22 under the corrected date cadence
  (tier 1 on 09-24, tier 2 on 10-01), so `discover_uploads` will legitimately
  spend 0 units on those two mornings. The new `due=` token is what keeps the
  healthcheck silent about it: a stage with nothing due is not a stage that
  failed. Whether those two days are in fact silent is itself part of the
  Gate 3 evidence.
- Then 3.5: re-derive sizing from `run_log` and `video_snapshots` over
  09-19..09-21 as steady state, with the method fixed in advance:
  **comments per video per tier from `video_snapshots.comment_count`** — the
  API's own count, not the number of rows harvested, which is capped by the
  per-tier page limit and would understate busy videos by construction; and
  **upload rates for tiers 1 and 2 from the lookback window of their sweeps**,
  not a three-day average, since those tiers are swept every 7 and 14 days and
  a flat average over three days would divide their uploads by the wrong
  interval.

  **Caveat, known now:** tier 1 is next due 09-24 and tier 2 on 10-01, so
  **neither is swept during 09-19..09-21**. Their upload rates must come from
  the 09-17 sweep, which covered their 8- and 15-day lookback windows under the
  same `upload_lookback_days` config. Only tier 0's rate is measured inside the
  steady-state window. Re-sweeping early to fix this was considered and
  **rejected** (2026-09-18): it would cost ~113 units and break the very
  cadence the gate is testing.

  Consequences, ruled 2026-09-18:

  - Tier 1 and tier 2 upload rates are labelled **single-window estimates from
    the 09-17 sweep**, not steady-state measurements.
  - The sizing is **scheduled for revision after the 10-01 tier-2 sweep**, by
    which point tier 1 will also have been swept twice more (09-24, 10-01).
  - The ceiling is computed from tier 0's steady-state rate together with the
    provisional tier-1 and tier-2 rates, and reported **with its sensitivity to
    a ±50% change in those provisional rates**, so the provisional status is
    visible in the number itself rather than only in a footnote.

  **The reference model needs adapting before it can be used.**
  `external/ytmon/ytmon/sizing.py` assumes a single homogeneous panel swept
  **daily**: `u_discovery = n_channels * upload_pages`, one unit per channel
  per day. Our pipeline is the opposite — per-tier cadences of 2/7/14 days are
  precisely what makes the frame affordable, and discovery costs
  `N_tier / cadence_tier` per day, not `N_tier`. Ported unchanged it would
  overstate discovery by 2x for tier 0 and by 7x and 14x for tiers 1 and 2,
  and so understate the panel ceiling badly. It also assumes one comment depth
  and one tracking window, where we have three of each (page caps 10/10/3,
  windows 30/14/7), and `comment_coverage=1.0`, where we now measure coverage
  directly and it is not 1.

  `src/sizing.py` will therefore be a tier-aware adaptation, not a
  transcription, and will state the tier mix it holds fixed when it answers
  "how large a frame fits the budget" -- a single scalar ceiling is not
  well-defined for a tiered frame without that assumption.

  **Report structure, agreed 2026-09-18:**

  *At 10k — report coverage, not a ceiling.* Headroom is already negative: the
  comment stage hit its share ceiling on every run to date, so the frame cannot
  be exhaustively collected at this budget and asking "how many more channels
  fit" is the wrong question. The answer reported instead is **sustainable
  coverage** under the current caps and windows: the share of tier-0 videos
  whose comments are harvested inside the tracking window, and the same for
  tiers 1 and 2.

  *At 1M — both ceiling readings, at the exhaustive-collection setting*, i.e.
  full coverage with the per-tier page caps removed, which is what 1M would
  actually be spent on:

  1. **Headline — tier-0 growth with tiers 1 and 2 held fixed.** How much the
     validated NewsGuard frame can grow; the reading closest to the research
     question.
  2. **Second — proportional scaling of the whole frame** at the current tier
     mix.

  Each with ±50% sensitivity on the provisional tier-1 and tier-2 rates.

  Note that removing the page caps makes `comments_per_video` drive cost
  directly -- pages become `ceil(comments / 100)` rather than the capped
  minimum -- which is why that input is measured from
  `video_snapshots.comment_count` rather than from harvested rows: at 1M the
  cap is gone and the API's own count *is* the cost.

  **Both blocks cite their measured inputs:** uploads per channel per day per
  tier; comments per video per tier from `video_snapshots.comment_count`;
  comments per unit observed; and discovery cost per tier per day under the
  cadences.

---

## 2026-09-16: Phase 3 deployed — cutover, crontab, first manual run

### Database cutover

**The cluster file is production as of `2026-09-16T10:47:44Z`.**

| | |
|---|---|
| Source | Mac `data/youtube_monitoring.db` |
| Destination | `gdelt-server:/data/ytmon/youtube_monitoring.db` |
| **md5, both ends** | **`b95825f215a9556d3e4333e5e961a03c`** |
| integrity_check | `ok` on both |
| Rows | channels 6,036 · videos 5,255 · comments 693,204 · channel_snapshots 5,737 · video_snapshots 5,255 — identical both ends |

The Mac copy is renamed `data/youtube_monitoring.replica.db`. Both entry points
refuse any path whose filename contains `replica` without
`--i-know-this-is-a-replica`, and the refusal is printed as a message naming
where production is, not as a traceback.

Two snags worth recording: macOS ships `openrsync`, which rejects
`--info=progress2`; and a verification command run against the not-yet-copied
path **created an empty database file** at the destination, which was
size-checked (0 bytes) and removed before the real transfer.

### API key

The daily project is deliberately **not** the project carrying the 1M request —
quota is granted per project, so sharing one would let the backfill and the
daily series starve each other. Verified by SHA-256 comparison, never by
printing either key:

```
Mac     config key   4b2e56292709d8c8…b03e40
Cluster .env         348fb7785a38d654…975ca1
```

### Crontab

62 lines before, 82 after, **purely additive — no existing line touched**.
Backup at `~/crontab.backup.20260916-124830`.

```diff
@@ -60,3 +60,23 @@
 3,13,23,33,43,53 * * * * /data/a4_inplace/drain_watchdog.sh >> ...
+
+# ytmon — YouTube monitoring pipeline.
+# Added 2026-09-16. Appended to the existing infosphere crontab; nothing else
+# in that file is touched by this deployment.
+#
+# Minutes are chosen to clear every job already scheduled on this box:
+# TAIWA run_live (*/15 at :00 :15 :30 :45), gdelt_update (every 5 at :02…:57),
+# gdelt_reconcile (:40), gdelt_reprobe (:50), drain_watchdog (every 10 at
+# :03…:53). The brief's 09:17 / 12:45 / 03:30 all collided with those.
+#
+# 09:18 Rome: the API quota resets at midnight US/Pacific, which is 09:00 Rome
+# under both DST regimes. The two zones shift within a couple of weeks of each
+# other; on those days the run starts up to an hour early or late, which the
+# governor tolerates because the ledger is keyed by Pacific day, not local day.
+
+CRON_TZ=Europe/Rome
+
+18 9 * * *   /data/home/infosphere/youtube_monitoring/deploy/run_daily.sh
+46 12 * * *  /data/home/infosphere/youtube_monitoring/deploy/healthcheck.sh
+34 3 * * *   /data/home/infosphere/youtube_monitoring/deploy/backup.sh
```

`CRON_TZ` is declared after every pre-existing job, so it applies only to the
ytmon lines; TAIWA and GDELT are unaffected.

### Interpreter

Deployed on **Python 3.12.3**, not the brief's 3.10. `python3.10 -m venv` on
this host produces a tree with **no pip** — `ensurepip` raises
`ModuleNotFoundError`, because the installed `python3.10-venv` is
`3.10.12-1~22.04.15`, a *jammy* package on a *noble* system — and there is no
passwordless sudo to repair it. 3.12 builds cleanly, the pinned requirements
install, and `pytest -q` is green in the cluster venv. Local development stays
on 3.10.12.

### First manual run — failed at stage 4, then succeeded

The first run **crashed in `harvest_comments`** after three stages. Three
defects, two of them invisible to the test suite:

1. **`TypeError: tuple indices must be integers`.** `_comment_queue` reads rows
   by column name, but `Database` never set `row_factory` — **and the test
   fixture set it itself**, so the stage passed every test and died in
   production. That is the actual defect: a fixture more capable than the thing
   it tests. `Database` now sets `sqlite3.Row`, the fixture no longer configures
   the connection, and a regression test drives the stage through a plain
   `Database` connection.

2. **5,248 videos were invisible to the comment queue.** Everything from the
   pre-daily backfill carries `comments_state` NULL, and the queue matches only
   `'pending'` or `'done'` — so their comments would never be harvested *or*
   re-polled, with no error anywhere. `scripts/adopt_backfill_videos.py` adopts
   them: 943 → `'done'` with `last_comment_count` seeded so the growth re-poll
   has a baseline, 4,305 → `'pending'`. **442 of those claim a non-zero
   `comment_count` while holding no comment rows** — either the pre-`bfbeda4`
   truncation or a backfill that never reached them. Worth noting for the
   paper's data-completeness section.

3. **Every log line was written twice** — a `FileHandler` on `pipeline.log`
   plus a `StreamHandler` on stderr, which the wrapper redirects into the same
   file. The stream handler is now attached only when stderr is a terminal.

### The successful run — `21ef37e46a97`

```
started  2026-09-16T11:09:57   finished 2026-09-16T11:35:09   (25m 12s)

stage              calls   units   items
resolve_channels       1       1      18    (28 queued, 10 unresolved)
discover_uploads   1,250   1,250  14,797   (1,143 / 2,741 due channels scanned)
refresh_videos       296     296  14,797   (0 unavailable)
harvest_comments   2,823   2,823  25,186   (2,679 / 31,734 videos)

quota_before 2,747   quota_after 7,117   units_spent 4,370
```

**All four stages non-zero**, which is the Gate 3 condition. Comments grew
693,204 → 718,390. Discovery and comments both stopped on their budget share
and left a backlog, which is the designed behaviour, not a failure.

### Ledger and the console cross-check

```
2026-09-15  playlistItems 1,711 · channels    71                 = 1,782
2026-09-16  playlistItems 3,564 · commentThreads 2,540 ·
            videos 641 · comments 283 · channels 89              = 7,117
```

**Today's ledger is not directly comparable to the new project's console.**
It opened at **723 units already spent from the Mac against the old project**
(the 2.5 channels pass and the tail of the recency sweep), before the cutover.

### The 1% check — failed at first, and found a real defect

```
console (daily project)                      6,666
ledger total today                           7,117
  less spent pre-cutover on the old project    723
  ─────────────────────────────────────────────────
  cluster portion of the ledger              6,394
  discrepancy                                  272   = 4.25%   FAILS the 1% gate
```

**Cause: 212 `commentsDisabled` 403 responses.** YouTube bills the request, not
the result — it served each of those and charged a unit — while `_call` charged
the ledger only on HTTP 200.

```
  cluster ledger                             6,394
  + 212 served-but-uncharged                   212
  ─────────────────────────────────────────────────
  adjusted                                   6,606
  console                                    6,666
  residual                                      60   = 0.90%   within 1%
```

The residual 60 units are **not explained** by anything in the logs. Candidates
are console aggregation lag and a handful of other billed errors, but neither
is evidenced, so it is recorded as unexplained rather than reasoned away.

**The reporting gap was the smaller problem.** The governor believed it had 212
more units than it did, so its refuse-before-calling guarantee was unsound: on
a day with many comments-disabled videos it could spend past the real ceiling
and hit a hard `quotaExceeded` instead of stopping cleanly. Fixed in `a4c5d37`:
`_call` now charges for every response the API *served* — 200,
`commentsDisabled`, and the not-found reasons — while refusals
(`quotaExceeded`, `dailyLimitExceeded`, rate limits) and transport failures
stay free, since those were never served. A test pins both halves, and one
earlier assertion that expected `ItemUnavailable` to cost nothing was corrected:
it encoded exactly this under-counting.

**From 2026-09-17 the ledger and console should agree directly**, since
everything runs on the cluster with the new key and the charging rule now
matches how the API bills. That agreement is itself part of the Gate 3 check.

### Also this session

`datetime.utcnow()` is deprecated from 3.12 and was producing 84 warnings per
test run. All 11 call sites now route through `src/timeutil.py`, whose body is
`datetime.now(timezone.utc).replace(tzinfo=None)` — the same naive UTC value,
byte-identical serialisation, no migration. Warnings are now zero.

That commit also **corrects a claim made earlier in this session**: aware
timestamps were said to sort before naive ones and corrupt ordering. That is
wrong for UTC — the offset is appended after the whole date and time, so string
order still tracks time order, and the test asserting otherwise failed. The
real hazard is **exact string equality**, which the snapshot primary keys, the
migration's timestamp join and the idempotent `INSERT OR IGNORE` all depend on:
a value written naive and looked up aware does not match, and it fails silently
as a duplicate row rather than an error. The aware migration stays deferred
indefinitely, for that reason rather than the one first given.

### Next

Nothing until three cron mornings have passed (2026-09-17, 18, 19 at 09:18
Rome). Gate 3 report after the third, including the console figure for the
1% check.

---

## 2026-09-16: 3.0 — per-tier discovery cadence

`playlistItems.list` costs a hard 1 unit per channel per visit, so a daily
sweep of the whole frame costs 4,312 units/day before any other stage runs.
That is what makes the primary frame alone unaffordable on a 10k key. Visiting
each tier on its own cadence fixes it.

### Cadence and projected cost

| Tier | Channels | Cadence | Units/day |
|---|---|---|---|
| 0 | 2,856 | every 2 days | 1,428.0 |
| 1 | 788 | every 7 days | 112.6 |
| 2 | 668 | every 14 days | 47.7 |
| | **4,312** | | **1,588** |

**Projected daily discovery cost: about 1,590 units** — a sixth of a 10k day,
where the daily sweep would have been 43%.

`schedule.upload_lookback_days` becomes per-tier at cadence + 1 (3 / 8 / 15),
so consecutive passes overlap and no upload can fall into the gap between them.

`share_discovery` is raised 0.15 → 0.20, and `share_comments` lowered 0.65 →
0.60 to match. At 0.15 discovery would receive about 1,490 units of a 10k day
against the 1,588 it needs, so tier 0 would slip its 2-day cadence
permanently. This is the kind of shortfall that shows up as a slow drift
rather than an error, so it is worth naming.

### 14-day simulation

4,312 channels, 10,000-unit daily budget, a fresh budget each day, the
channels stage charged first:

```
tier 0: n=2,856  visits min=7 max=7  mean 7.00
tier 1: n=  788  visits min=2 max=2  mean 2.00
tier 2: n=  668  visits min=1 max=1  mean 1.00
total visits 22,236        mean 1,588 units/day
```

Every tier-0 channel is visited at least 7 times and every tier-2 channel at
least once, which is the requirement. Days 0-2 hit the discovery share and
left a backlog — 4,312 due, 1,982 scanned — which the oldest-first ordering
within each tier drained by day 3. That is the property that keeps a channel
from starving: a channel skipped on budget is not stamped as discovered, stays
due, and keeps its place at the front of the queue.

New column `channels.last_discovered`, carried across `INSERT OR REPLACE` like
the other pipeline columns, so a backfill re-insert cannot silently reset a
channel's cadence.

---

## 2026-09-16: Phase 2 CLOSED

Tier 2 admitted after tightening, alternates linked, coverage audited, frame
exported. **No quota spent on any of this work** — every input is an archived
API response or a free Wikidata query. Phase 2 total remains 2,505 units.

### Final tier table

| Tier | Rows | Composition | Collected |
|---|---|---|---|
| 0 | 2,856 | validated NewsGuard frame | yes |
| 1 | 788 | Wikidata outlets, topic-confirmed and active (779) + alternates of tier-0/1 canonicals (9) | yes |
| 2 | 668 | 319 individuals (Politics-confirmed) + 357 dormant topic-matched outlets, less alternates moved | yes |
| 3 | 1,724 | recorded, never collected | no |
| | **6,036** | | |

`collect_tiers: [0, 1, 2]`. Tier 3 is excluded unconditionally in code, not
merely by config.

### The three Gate 2 rates

| Stratum | Result |
|---|---|
| Tier 1, `topic` | **0/25 = 0%** (threshold 5%) — passes |
| Tier 2, redraw under rule (a) | **4/50 = 8%** (threshold 15%) — passes |
| Tier 2, pooled with the earlier in-scope rows | **4/63 = 6.3%** |

The strata that failed were removed rather than argued with: tier-1
`title_only` at 68% and tier-2 `title_only` at 96% both went to tier 3, 309
outlet rows in total, tagged `:gate2_fp68`. Tier-2 individuals were tightened
by rule (a), Politics topic required, moving 125 to tier 3 and keeping 319.

Dormant topic-matched outlets stayed at tier 2 rather than being dropped:
they passed at 0%, recency is a cost question rather than a precision one, and
an outlet that resumes publishing is itself a finding.

### 2.4 alternates

101 Wikidata items map to more than one channel in the database; 126
alternates linked via `alt_of`, 40 of them at tier 0-1 and so actually
collected. The canonical is chosen by token overlap with the Wikidata label,
then `videoCount`, then `channel_id` for determinism. Sitelink count is used
nowhere — it is a fame proxy and the brief allows it only as a tie-breaker,
which the first two criteria never needed.

**A bug caught by the tier counts moving.** The first version let an alternate
inherit its canonical's tier unconditionally, which promoted 4 channels *into
tier 0*. Tier 0 is defined as the validated NewsGuard frame, so that quietly
redefined the primary frame and would have invalidated every count already in
this logbook. Alternates are now capped at tier 1. The 35 affected rows were
repaired by recomputing their tier from the archives, and tier 0 was verified
against `validation_progress.json` to match exactly — 2,856, with no
difference in either direction. A test now pins the invariant.

### 2.5 coverage audit

`scripts/audit_frame_coverage.py` → `reports/`.

**A. NewsGuard failures with a Wikidata channel: 66 of 440.** All 66 are
already in the database through the Wikidata route, so none needs the 1-unit
re-validation the list was meant to surface. **17 sit at tier 3** — held but
never collected — and are the actionable half.

**B. Frame gap: 772 of 788 tier-1 outlets are absent from NewsGuard**, led by
the United States (93), India (32), Russia (26) and Ukraine (24), with 149
carrying no country. This is the limitations-section finding: the sampling
frame is NewsGuard's coverage, which is uneven by country and skews to outlets
large enough to have been rated.

Brand matching was tightened twice against its own output — a single shared
token matched *L'Humanité* to *L'essentiel*; plain containment then matched
*Press TV Français* to *The News-Press* and *Radio Gong 96.3* to *3 News*,
because a one-token label swallows anything containing it. Equal token sets,
or containment with two or more tokens, cut the list from 210 to 66. Both
lists are candidates for review, not verified mappings: shared names survive
any token matching (*La Tribune* / *The Tribune*), and `match_method` is
recorded per row.

### Country provenance

Of 315 individuals at tier 1-2, 261 take the country from `snippet.country`,
50 fall back to Wikidata `P27`, 4 remain unknown and are left NULL rather than
guessed. Every fallback row carries `:country_from_citizenship` on its reason,
so the Milei class of error — an Argentine politician with Italian citizenship
filed under Italy — is greppable in the data rather than described in a
comment.

### `data/frame_tiers.csv`

6,036 rows with the brief's columns plus `alt_of`. The `reason` column
accumulates suffixes and reads as the decision history:
`topic+title:politics`, `title_only:gate2_fp68`,
`topic:stale:country_from_citizenship`. Labels prefer the channel's own title
over the seed label, because 149 seed labels are bare QIDs; 6 rows have no
usable label and are left empty rather than filled with an identifier
pretending to be a name.

### Out of scope, still open

- Phase 3 in full: cluster deployment, `deploy/` scripts, cron, healthcheck,
  backup rotation, the sizing re-derivation.
- `SERVER_MIGRATION_GUIDE.md` still needs its superseded-by notice.
- The 17 tier-3 promotion candidates from audit list A.
- The 286 contaminated `/c/` and `/user/` validation URLs, still blocked on
  the 1M quota approval.

---

## 2026-09-16: Tier 2 rule selection and redraw (branch `feat/tier2`, no quota)

Gate 2 left tier 2 failing at 20% against a 15% threshold. This selects a
tightening from the archived responses and redraws the hand check. **No quota
spent** — every input is `data/raw/wikidata_confirm/` plus
`data/wikidata_occupations.json`.

### Scope

Tier 2 holds 1,110 rows, but only **444 are individuals**, and rules (b) and
(c) are occupation-based, so they only bite there. The other 666 are stale
outlets (567) and the outlets demoted from tier 1 by Gate 2 (99); they are
untouched by this.

Of the 50 tier-2 rows hand-checked at Gate 2, **25 remain in scope** — the 25
`title_only` rows were demoted to tier 3 and are no longer tier 2. Rates below
are against those 25, and against the subset of them each rule keeps.

### Rule comparison

| Rule | Rows kept (of 444) | Checked rows kept | FP | FP rate |
|---|---|---|---|---|
| current (no tightening) | 444 | 25 | 5 | 20% |
| **(a) Politics topic required** | **319** | 13 | 0 | **0%** |
| (b) all-news occupations only | 303 | 17 | 3 | 18% |
| (c) both | 224 | 9 | 0 | 0% |

(a) and (c) are tied at 0%; (a) keeps 95 more rows, so the tie breaks to (a).
(b) is 18 points clear of (a) and fails on its own, so it is not tied with
anything. **Rule (a) selected.**

The ranking denominators are small — 13, 17 and 9 rows — so this only orders
the candidates. The redraw is what decides the gate, as intended.

### Redraw under rule (a)

50 rows drawn at random (seed 2026) from the 306 rule-(a) rows not already
hand-checked, recorded with verdicts in `data/gate2_redraw.csv`.

| | |
|---|---|
| n | 50 |
| False positives | **4** |
| **Rate** | **8%** |
| Threshold | 15% |
| **Result** | **PASSES** |

Combined with the 13 rule-(a) rows checked earlier (0 false positives):
**4/63 = 6.3%**.

The four false positives are all Wikidata-classified journalists whose channel
is something else:

| Channel | Why |
|---|---|
| Myrka Dellanos Show | Emmy-winning broadcast journalist; the channel is faith and lifestyle |
| potholer54 | former science journalist; debunks science misinformation |
| Historia con Patricio Lons | history and hispanist advocacy |
| АНДРІЙ ДАНІЛЕВИЧ | primarily a sports broadcaster |

Three further rows were judged ok but are genuinely borderline and are flagged
in the CSV: a Ukrainian talk-show host with heavy human-interest content, a
Japanese conspiracy lecturer who calls himself a journalist (political
content, so in scope for a polarization study, but not a journalist in any
ordinary sense), and one channel with 320 subscribers and no description that
could not be verified from the archive alone. Counting all three as false
positives would give 7/50 = 14%, still under the threshold.

### Status

Rule (a) is selected and validated but **no tiers have been changed**; the
tier-2 population is still the untightened 444 individuals, and
`collect_tiers: [0, 1]` still excludes tier 2 from collection. Applying rule
(a) would move 125 individuals from tier 2 to tier 3 and leave 319.

---

## 2026-09-16: Phases 1 and 2 merged to production; raw archives backed up

### Merge and tag

`feat/daily-monitor` merged into `production` as **`670bf86`**, with `--no-ff`
so the two provenance boundaries keep their hashes and stay quotable:

| Commit | Boundary |
|---|---|
| `bfbeda4` | before it, the client could truncate video and comment collection on quota exhaustion and record it as complete or comments-disabled |
| `eab26e1` | before it, `INSERT OR REPLACE` reset `tier`, `uploads_playlist` and `comment_cursor` |

Tagged **`ytmon-merge-p1p2`** (annotated, `b400599` → `670bf86`). Both pushed;
`origin/production` and the local branch are identical, and the tag is
confirmed present on the remote.

The push initially failed twice, for reasons worth recording in case they
recur: the SSH identity `donaldruggiero-losardo-csl` is not authorised on
`losardor/youtube-monitorin-pipeline`, and the HTTPS fallback was rejected
because the `gh` OAuth token lacked `workflow` scope while the push carried
`033edee` (2026-04-20, pre-existing and unpushed since April), which adds
`.github/workflows/tests.yml`.

### Scope gating

`config/config_daily.yaml` gains `collect_tiers: [0, 1]`. Tier 2 is excluded
from collection until it passes Gate 2. All four stages are gated, not only
the channels stage: `refresh_videos` and the comment queue would otherwise
have kept re-stat'ing and re-polling tier-2 videos already in the table.
Tier 3 is filtered out unconditionally, so no configuration can opt into
collecting rows recorded never to be collected. `data/.ytmon.lock` is now
gitignored.

### Raw response archives backed up

Both archives hold the API responses behind the phase 2 tiering — 2,447 quota
units of spend. `wikidata_confirm` is tracked in git; `wikidata_recency` is
gitignored and existed only on the workstation disk until this backup.

| | |
|---|---|
| Tarball | `wikidata_raw_20260916.tar.gz` |
| Destination | `gdelt-server:/data/ytmon/backups/` (`infosphereVM`, created this session) |
| Size | 7.0 MB |
| **md5 (both ends)** | **`5c16453b200b2abf5224b659f40cd3b7`** |
| Contents | 2,451 entries — 73 `wikidata_confirm/*.json`, 2,376 `wikidata_recency/*.json` |

Verified by comparing md5 locally and on the server, listing the archive
remotely, and extracting it there.

**Built with `COPYFILE_DISABLE=1`.** The first attempt used plain macOS `tar`,
which bundled an AppleDouble `._` sidecar for every file: the md5 matched on
both ends, but the archive held 4,898 `.json` entries instead of 2,449, half
of them binary xattr stubs that are not JSON. A restore globbing `*.json`
would have picked them up. The earlier tarball
(`1b7bcdaf64559c7b88622d639d02070e`) was replaced in place and should not be
used.

---

## 2026-09-16: Phase 2 — Wikidata pool tiered (Gate 2: tier 1 passes, tier 2 fails)

Branch `feat/daily-monitor`, continuing from phase 1. Loads the validated frame
into the production database, tiers the 17,094-channel Wikidata pool, and runs
the first daily channels pass.

### Quota spent

| Pacific day | Endpoint | Calls | Units |
|---|---|---|---|
| 2026-09-15 | channels.list | 71 | 71 |
| 2026-09-15 | playlistItems.list | 1,711 | 1,711 |
| 2026-09-16 | playlistItems.list | 665 | 665 |
| 2026-09-16 | channels.list | 58 | 58 |
| | **total** | **2,505** | **2,505** |

Breakdown by purpose: confirmation pass 71, recency pass 2,376 (1,711 + 665
across the day boundary), first daily channels pass 58. Every response is
archived, so all of it can be recomputed for free.

The run crossed the Pacific midnight, which is the first live demonstration
that the ledger's billing-day key works: the 1,782 units spent before the
rollover stayed on 2026-09-15 and the governor handed out a fresh budget on
2026-09-16 without being told to.

### 2.0 — the frame is loaded; this is now the production database

`data/youtube_monitoring.db` md5 `795bb971…` → `0554f12b…` across the phase.

| | before | after |
|---|---|---|
| channels | 31 | 2,858 → 6,036 after tiering |
| tier 0 | — | 2,856 |
| videos / comments | 5,255 / 693,204 | unchanged throughout |

2,827 channels inserted, 29 updated in place (statistics, titles and snapshots
untouched), 2 marked tier 3. All 2,867 validated URLs joined `sources.csv`
exactly; every loaded channel carries a NewsGuard rating.

**Validation statistics loaded as real observations** (`scripts/backfill_validation_snapshots.py`):
`channel_snapshots` 31 → 2,887, spanning `2025-12-11T16:58:23` ..
`2026-04-21T14:03:41`. 2,845 of 2,856 tier-0 channels carry an observation;
the other 11 recorded no statistics at validation time. 40 channels already
had two observations (29 November collections + 11 channels validated from two
URLs on two dates). `view_count` and `hidden_subscribers` are NULL on every
validation row — the validator never observed them, which is not zero.

**Consequence:** the daily channels pass is the *next* observation, not the
first. After the 2.5 pass the table holds 5,737 rows and 2,839 channels have
two or more observations, so the series has real deltas from day one.

### 2.1–2.3 — filters

| Step | Count |
|---|---|
| Wikidata channels already in tier 0 (wd_item/wd_class attached) | 428 |
| `stratum='outlet'` | 2,156 |
| — pass class filter | **2,156 (0 rejected)** |
| — already tier 0, skipped | 240 |
| — to confirm | 1,916 |
| `stratum='commentator'` distinct | 4,672 |
| — QIDs queried for P106 / with occupations | 4,386 / 4,379 |
| — pass occupation filter | **1,267** (849 all-news, 418 news-majority) |
| — rejected: no news occupation / disqualifying / news minority | 1,879 / 946 / 580 |
| — to confirm | 1,262 |

**The class filter is a no-op on this pool.** All 2,156 outlet rows already
carry at least one of the eight news classes, because the stratum was defined
upstream by exactly that test. `mass media` occurs 1,240 times but always
beside `newspaper` or `news media`, so the carrier-only exclusion never fires
either. The brief's 2.2 class filter restates its own input, and the whole
burden of precision therefore falls on the YouTube-side checks. The filter is
kept as written so a noisier pool would still be narrowed.

### The brief was wrong about `News`

The topic check was specified as `News`, `Politics`, `Society`, `Business`.
**`News` does not occur once** across the 3,423 channels in the confirmation
pass. `Business` occurs 45 times. In practice the check is Society (58.8% of
outlet candidates) or Politics (36.6%). `News` is dropped from
`TOPIC_SUFFIXES`; keeping it implied a precision it never delivered.

### Rule calibration against labelled positives

The 240 Wikidata outlets already in tier 0 are known-good news channels that
reached the frame independently through NewsGuard, so the fraction a rule keeps
is a retention rate.

| Rule | Labelled kept (240) | Candidates passed (1,916) |
|---|---|---|
| resolved + has videos | 238 (99.2%) | 1,793 (93.6%) |
| topic only | 189 (78.8%) | 1,136 (59.3%) |
| title only | 198 (82.5%) | 1,163 (60.7%) |
| topic OR title | 233 (97.1%) | 1,558 (81.3%) |
| topic AND title | 154 (64.2%) | 741 (38.7%) |
| **topic OR (title & not gaming/music)** | **228 (95.0%)** | **1,445 (75.4%)** |

Requiring a topic match discards 21.2% of known-good outlets, and they are
systematically local newspapers — The Providence Journal, Wichita Eagle, The
Baltimore Banner, La Provence, The Herald-Dispatch — tagged Sport or Lifestyle
because that is what their video output is. Sport is therefore **not** a
disqualifying topic; gaming and music are.

### Tier assignment

Rule: `topic OR (title AND not gaming/music-tagged)`, recency = newest upload
within 180 days. `channels.tier_reason` records the admitting check.

| | outlets | individuals |
|---|---|---|
| admitted | 1,445 | 932 |
| fresh | 878 | 532 |
| stale | 567 | 400 |
| rejected (unresolved / zero-video / no match) | 471 | 330 |

### Gate 2 — stratified hand check of 100 rows

Criterion: is this channel a news outlet / news commentator **for a study of
polarization and trust in news media**? Specialist sports, tech, science,
health, lifestyle and entertainment publishers count as false positives even
when the publisher is a real periodical or the person is a real journalist —
the channel is not news. Verdicts recorded in `data/gate2_sample.csv`.

| Stratum | n | FP | rate |
|---|---|---|---|
| tier 1 `topic` | 25 | 0 | **0%** |
| tier 1 `title_only` | 25 | 17 | **68%** |
| tier 2 `topic` | 25 | 5 | **20%** |
| tier 2 `title_only` | 25 | 24 | **96%** |

Pooled: tier 1 34% over the sample, **7.7% population-weighted** (the sample
over-represents `title_only`, which is 11% of tier 1). Tier 2 individuals 58%
over the sample, **32.6% population-weighted**.

**Demotions applied**, per the stratum rule:
- tier 1 `title_only` (99 rows) → tier 2, reason `title_only:gate2_demoted`
- tier 2 `title_only` (88 rows) → tier 3, reason `title_only:gate2_demoted`

**After demotion: tier 1 = 779 rows at 0% false positives — PASSES (≤5%).**

**Tier 2 still FAILS: 444 individual rows at 20%, above the 15% threshold.**
Per the brief, do not ship tier 2; tighten 2.3 and rerun. The tier-2 failures
are journalists whose *channel* is lifestyle, science, health or trade tech —
they pass on `Society`, which is too broad to discriminate.

Tightening options, computed free from the archive:

| Option | Tier-2 individuals retained |
|---|---|
| current (Society, Politics or Business) | 699 |
| require Politics | 477 |
| exclude lifestyle/health/entertainment/sport topics | 440 |
| require Politics AND exclude those | 351 |

Requiring `Politics` removes **all 5** false positives from the hand-checked 25
while keeping 13 of them — 0% on that subsample, n=13. That is the recommended
tightening, pending a decision and a fresh Gate 2 draw.

### Final tier distribution

| Tier | Count | Meaning |
|---|---|---|
| 0 | 2,856 | validated NewsGuard frame |
| 1 | 779 | Wikidata outlets, topic-confirmed, active (Gate 2 passed) |
| 2 | 1,110 | stale outlets, demoted title-only outlets, individuals (Gate 2 **not** passed) |
| 3 | 1,291 | recorded, never collected |

### 2.5 — first daily channels pass

`daily.py run --stages channels --max-tier 0 --budget 9000`

```
run_id f46c844984aa   queued 2,856   resolved 2,850   unresolved 6
units 58   calls 58   elapsed ~8s
```

2,850 tier-0 channels now have `uploads_playlist` and `status='active'`; 6 are
marked `unresolved` and kept. Discovery can run without a single `search.list`
call.

### Changes made while running phase 2

1. **Tier 3 was collectable.** The daily channels stage had no tier filter, so
   it would have resolved tier-3 rows — the ones explicitly recorded never to
   be collected — and tiers 1 and 2 when only tier 0 was wanted. Added a
   hard tier-3 exclusion plus `limits.max_tier` / `--max-tier`, with tests.

2. **13 rows carry a pipe-joined QID pair** (`Q20963418|Q4160936`): one channel
   mapped to two Wikidata items. Passed through raw this builds `wd:Q1|Q2`,
   invalid SPARQL, which 400s the whole batch — the first occupation fetch lost
   2,250 good QIDs to 9 poisoned batches. QIDs are now regex-extracted and a
   failing batch bisects.

3. **The occupation sets were audited against the labels actually present**
   rather than left as guessed, lifting passes from 782 to 1,267. Added
   political pundit, freelance/broadcast/video journalist, editorial columnist,
   media critic and the domain journalists. Deliberately excluded as adjacent
   but not news: sports/baseball/esports/color commentator; film/video/
   television/literary editor; media manager, media scholar, media personality.

4. **The recency pass lost its work to one DNS blip.** It died at 1,711 of
   2,377 on a `ServerNotFoundError` and, because it batched all database writes
   to the end, wrote nothing — 1,711 units would have been wasted had the
   responses not been archived. Transport failures are now per-channel and
   non-fatal (the channel is left undecided for a retry), and tier writes flush
   every 200 rows.

5. **A migration test asserted a global row count** — `channel_snapshots` equals
   the number of timestamped channels — which stopped being true the moment the
   table held observations from more than one source. Rewritten to assert the
   real invariant: every timestamped record has a snapshot at its own timestamp,
   plus idempotence. It would have gone red on every future daily run.

### Open

- **Tier 2 is not shippable.** Tighten 2.3 and redraw Gate 2.
- 2.4 (multi-channel items, `alt_of`) and 2.5's coverage audit
  (`scripts/audit_frame_coverage.py`) are not done.
- `data/frame_tiers.csv` is not yet emitted; the tiering lives in the database.
- Country-for-persons handling (`reason='country_from_citizenship'`) not done.

---

## Notes

### Quota Costs (YouTube Data API v3)
- `channels.list` (by ID): 1 unit
- `channels.list` (forUsername/forHandle): 1 unit
- `search.list` (fallback): **100 units** ← main quota drain
- Daily quota: 10,000 units (standard) or 1,000,000 (production)

### Known Issues
1. `/c/` and `/user/` URLs may trigger expensive search fallback when `forUsername` fails
2. Some channels are genuinely deleted/private/suspended
3. URL-encoded characters in channel names (German, French outlets)

---

## 2025-12-23: URL Cleanup Pass (undocumented at the time)

Non-API data-quality work, no validation quota consumed.

- **442 URL normalizations** applied to `sources.csv` (strip trailing `/`, `/videos`, `/featured`, `?app=desktop`; decode `%C3%A4` → `ä`; split comma-joined dual URLs — keep first).
- Produced `data/validation/corrected_urls_validation.csv` (69 rows): hand-corrected URLs for rows where the original was a bare name, video link, playlist link, or non-YouTube domain. 68 of 69 resolved; 1 failed (`arretsurimages.net`) — replaced in `sources.csv` with an unrelated channel.
- Backups: `data/sources_backup_20251223_112346.csv`.
- Outcome NOT merged into `validation_progress.json` at the time → created dedup drift, picked up in the 2026-04-20 reconciliation below.

---

## 2026-04-20: Reconciliation After 4-Month Gap

Session resumed after pipeline last touched 2025-12-15. Status-check discovered on-disk state diverged from LOGBOOK claims in several ways. Reconciled before running Validation Run #3.

### What diverged
1. **LOGBOOK Run #2 said "1,000 URLs / 772 success"**; actual `validation_progress.json` bucketing shows **1,050 / 772**. LOGBOOK had rounded down. This accounted for the "+50" apparent mystery.
2. **Dec 23 URL cleanup** (442 row changes in `sources.csv` + 69-row `corrected_urls_validation.csv`) was never merged into `validation_progress.json` → dedup would have re-queried hundreds of already-validated URLs in Run #3.
3. **`collection_runs` row #6** stuck in `status='running'` since 2025-11-21 (no heartbeat, no end_time). Run #4 (2025-11-19) is in the same state — flagged but not yet aborted.
4. **DB channel count** (31) does not match LOGBOOK's "73" — not yet investigated.

### Actions taken
- **Dedup logic audit** (`scripts/validate_channels.py:148-149`): confirmed dedup is a plain URL-string set-membership check. No channel_id key. Consequence: any URL edit invalidates the dedup.
- **Merged `corrected_urls_validation.csv` into `validation_progress.json`**: 11 new successful entries added; 57 were already validated (same `@handle` present in a different sources.csv row originally); 1 failure skipped.
- **Re-keyed normalized URLs**: rebuilt `validated` + `results` from row-by-row diff of `sources_backup_20251211_171901.csv` → `sources.csv`. 288 unique old-URL keys from 442 row changes. 1 pure rewrite, 110 stale duplicates dropped (both pre- and post-normalization forms had been validated independently), 177 never validated (no-op).
- **Backup before mutation**: `data/validation/validation_progress.json.bak_before_reconcile_20260420` (gitignored, local-only).
- **Aborted `collection_runs` row #6**: `status='running'` → `status='aborted'`, `end_time='2026-04-20T11:22:00'`, reason logged. Run #4 left as-is pending review.
- **Dry-run of Run #3**: reused validator's own `get_unique_urls` + dedup filter without API calls.

### State after reconciliation
| Metric | Pre | Post |
|---|---|---|
| `validated` count | 2,393 | **2,294** |
| Unique URLs in `sources.csv` | 3,307 | 3,307 |
| Would-query count for Run #3 | — | **1,013** |

The 2,294 number is the truth: 2,393 Dec-15 entries − 110 duplicates (pre/post-normalization pairs) + 11 merged corrected URLs. The +49 over LOGBOOK's "964 remaining" estimate is just the LOGBOOK using the rounded 2,343 number instead of the actual 2,393.

### Run #3 plan (not yet executed)
- **Expected**: 1,013 API lookups. Shape breakdown: 854 `/channel/UC...` (1 unit each), 93 `/c/`, 42 `/user/`, 22 `/@`, 2 bare/other.
- **Worst-case quota**: ~16,554 units (well under 1M daily).
- **Still TBD before run**: decide on run #4 abort; decide on DB 31-vs-73 discrepancy.

---

## Known bugs

### `youtube_client.get_channel_info` swallows quota 403 as "not found" — FIXED 2026-09-15

When the YouTube API returns a `quotaExceeded` 403, the client currently catches the error and returns `None`, which the validator records as a resolution failure ("Channel not found"). This contaminated the tail of Dec 15's Run #2: the last ~137 entries with `cost=0` + `"Channel not found"` are likely valid channels, not invalid ones.

After the 1M quota is approved (or on any day with spare quota), re-validate any URL in `validation_progress.json` matching the pattern `cost=0 AND status=failed AND reason="Channel not found"`.

Client fix: catch the 403 explicitly, raise `QuotaExceededError`, stop cleanly. Out of scope for Run #3.

**RESOLVED 2026-09-15 (phase 1.2, commit `bfbeda4`).** Every API call now routes through `YouTubeAPIClient._call`, which raises `QuotaExhausted` on a 403 with reason `quotaExceeded`/`dailyLimitExceeded` and charges the ledger only on HTTP 200. The blanket `except Exception -> return None` is gone from `get_channel_info` and `get_channel_by_username`, and the same swallow was found and fixed in three further methods (`get_channel_videos`, `get_video_details`, `get_video_comments`). Regression test: `tests/test_daily.py::test_quota_403_raises_and_leaves_the_channel_row_untouched`. The 286 remaining contaminated `/c/` and `/user/` entries are still outstanding and still blocked on the 1M quota approval; `scripts/revalidate_contaminated.py` remains the tool for them.

**Update 2026-04-21 — Partial mitigation applied via Run #3d.** The cheap bucket (/channel/UC, /@handle) has been re-validated using `scripts/revalidate_contaminated.py`, which bypasses the bug by calling `_make_request` directly. 647 contaminated entries re-queried; 615 recovered to success, 32 confirmed failed. The underlying bug in `src/youtube_client.py:196-198` (blanket `except Exception` in `get_channel_info`) is still present. **Still outstanding:**
- **Code fix** to `get_channel_info`: let quota 403 propagate as `HttpError` (or a named subclass) instead of returning `None`.
- **Remaining contamination**: 286 entries with `/c/` (161) and `/user/` (125) forms — worst-case 28,600 units to re-validate, blocked until 1M quota approval.
- Any future main-collection run (`collect.py`) still uses the buggy `get_channel_info` and is at risk of silent data loss if it hits quota exhaustion.

### Truncated channel ID in `validation_progress.json`

During Run #3d (2026-04-21), `revalidate_contaminated.py` crashed on a 23-character channel ID (`UCmgnsaQIK1IR808Ebde-ss` — valid YouTube channel IDs are 24 chars: `UC` + 22). Script was patched to tolerate and re-ran cleanly. Root cause not investigated — some earlier validation path wrote a malformed ID into `validation_progress.json`. Low priority; flagged in case it resurfaces during main collection (`collect.py` may pass channel IDs to API calls assuming them well-formed).
