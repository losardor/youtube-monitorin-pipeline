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

### Validation Run #3 (pending - needs quota reset)
- **Remaining**: 964 URLs
- **Estimated quota**: ~10,000 units (should complete in one run)
- **Status**: Waiting for quota reset...

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
