# YouTube Monitoring Pipeline - Logbook

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

### `youtube_client.get_channel_info` swallows quota 403 as "not found"

When the YouTube API returns a `quotaExceeded` 403, the client currently catches the error and returns `None`, which the validator records as a resolution failure ("Channel not found"). This contaminated the tail of Dec 15's Run #2: the last ~137 entries with `cost=0` + `"Channel not found"` are likely valid channels, not invalid ones.

After the 1M quota is approved (or on any day with spare quota), re-validate any URL in `validation_progress.json` matching the pattern `cost=0 AND status=failed AND reason="Channel not found"`.

Client fix: catch the 403 explicitly, raise `QuotaExceededError`, stop cleanly. Out of scope for Run #3.

**Update 2026-04-21 — Partial mitigation applied via Run #3d.** The cheap bucket (/channel/UC, /@handle) has been re-validated using `scripts/revalidate_contaminated.py`, which bypasses the bug by calling `_make_request` directly. 647 contaminated entries re-queried; 615 recovered to success, 32 confirmed failed. The underlying bug in `src/youtube_client.py:196-198` (blanket `except Exception` in `get_channel_info`) is still present. **Still outstanding:**
- **Code fix** to `get_channel_info`: let quota 403 propagate as `HttpError` (or a named subclass) instead of returning `None`.
- **Remaining contamination**: 286 entries with `/c/` (161) and `/user/` (125) forms — worst-case 28,600 units to re-validate, blocked until 1M quota approval.
- Any future main-collection run (`collect.py`) still uses the buggy `get_channel_info` and is at risk of silent data loss if it hits quota exhaustion.
