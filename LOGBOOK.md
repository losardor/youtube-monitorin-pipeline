# YouTube Monitoring Pipeline - Logbook

## Current Status (as of 2026-09-15)

**Current phase:** Phase 1 of the ytmon merge complete (Gate 1 passed, branch `feat/daily-monitor`). Phase 2 (Wikidata tiering) not started.

- **Validated URLs:** 3,307 / 3,307 (100%)
- **Confirmed channels:** 2,867 (86.7% success rate after Run #3d recovery pass)
- **Deferred:** 286 expensive bug-contaminated entries (`/c/`, `/user/`) — re-validation blocked on 1M quota approval
- **Main collection:** blocked on 1M quota approval (request submitted 2026-04-20, response pending)
- **403-swallow bug:** **FIXED 2026-09-15** in phase 1.2 — was present in five methods, not one. See the 2026-09-15 entry.
- **Validated frame location:** `data/validation/validation_progress.json` (2,867 successes, 2,856 distinct ids). Not yet loaded into the database, which still holds only the 31 Nov 2025 channels.
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
