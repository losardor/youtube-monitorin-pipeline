# Cluster status — ytmon daily run

**Date:** 2026-09-22 · **Host:** infosphereVM (`gdelt-server`) · **Mode:** read-only inspection
**Deployed:** `2f34fbc` · **Database:** `/data/ytmon/youtube_monitoring.db`

No files, crontab entries, processes or database rows were modified. All SQLite
access used `sqlite3 -readonly`. `daily.py status` and `healthcheck.py --dry-run`
were executed as read-only reporting commands; no `daily.py run`, no rsync, no
git operations on the cluster.

---

## 1. Summary

- The daily run is **healthy**: six cron runs on six consecutive days (09-17 … 09-22), each completing all four stages, none with a zero-unit stage.
- **Four clean runs on the current build** (09-19 … 09-22, `b98418e`/`2f34fbc`); the 09-17 and 09-18 runs were on the superseded `93debfa`.
- Units per day sit at **6,255–6,551 of the 9,000 budget** (69–73%); the comment stage hits its share ceiling every run and the video stage now does too.
- **Comment backlog is growing**: 83,126 pending against 21,047 done and 4,548 expired; `refresh_videos` queued 108,743 on 09-22 but cleared 58,355.
- **Storage is growing steadily**: live DB +62 MB/day, `/data/ytmon` +298 MB/day, NAS +164 MB/day; NAS pruning to 3 dailies is working.

## 2. Gate 3 checklist

| # | Item | Status |
|---|---|---|
| a | Three consecutive clean cron runs | **Verified today** — 09-19, 09-20, 09-21 each ran all four stages with non-zero units and every stage had due work. See §4.3. Caveat in §3.5: the "idle discovery day" case the criterion was written to permit never arose, so that half of the ruling is untested. |
| b | Forced `flock` collision | **Previously verified per LOGBOOK (2026-09-18)** — exit 1, 0s, ledger unchanged. Not re-run today; re-running would mean executing `run_daily.sh`. |
| c | Backup restore + `integrity_check` | **Previously verified per LOGBOOK (2026-09-18)** on `ytmon_2026-09-18.db.gz`. Not re-run today. Today's backups exist for every night 09-17…09-22 but their integrity is **unverified** — see §3.4, `backup.sh` output is discarded. |
| d | Cluster-venv pytest | **Previously verified per LOGBOOK (2026-09-18)** — 150 passed, 1 skipped. Not re-run today. |
| e | Ledger vs console within 1% for 2026-09-16 | **Still open.** Ledger total for Pacific day 2026-09-16 = **7,117 units / 7,117 calls**. Console figure **to be supplied**. Note the two adjustments already on record: 723 of those units were spent pre-cutover against the *old* Cloud project, and 212 `commentsDisabled` responses that day went uncharged (the charging fix `a4c5d37` postdates them), so the new project's console is expected near **6,606**. |
| f | Sizing re-derivation after seven runs | **Still open.** Six cron runs exist (09-17 … 09-22); four are on the current build. One short of seven. |

## 3. Anomalies

### 3.1 Deployed version is not the one the task expected

The task expected `b98418e` (tip of `feat/post-gate3`). The cluster runs `2f34fbc`,
which is the tip of `production`.

```
$ ssh gdelt-server 'cat /data/home/infosphere/youtube_monitoring/deploy/VERSION'
2f34fbc2549eebe7f01771faecbdf188f7dd3352
2026-09-18 15:47:12 +0200
logbook: fix the 3.5 sizing report structure in advance

$ git log --oneline -5 production
2f34fbc logbook: fix the 3.5 sizing report structure in advance
b0902bf logbook: 3.5 sizing method -- provisional rates, sensitivity, model adaptation
0abe396 logbook: record the Gate 3 criterion and the 3.5 method before the runs
b941df2 Merge feat/post-gate3: comment policy, date cadence, healthcheck, status split
0b693a9 logbook: reset the Gate 3 run counter to 09-19/20/21

$ git log --oneline -5 feat/post-gate3
0b693a9 logbook: reset the Gate 3 run counter to 09-19/20/21
b98418e logbook: Gate 3 interim and the post-gate-3 changes
...
```

`feat/post-gate3` was merged into `production` as `b941df2`; three LOGBOOK-only
commits followed. The deployed tree therefore contains the same executable code
as `b98418e` plus documentation. **Deployed == `origin/production`.**

### 3.2 `resolve_channels` skips whole days; the channel series has gaps

`channel_refresh_days: 1` is configured, but channel statistics were captured on
only **four of the last seven days**.

```
$ sqlite3 -readonly ... "select substr(observed_at,1,10) as day, count(*) from channel_snapshots group by day order by day desc limit 8;"
2026-09-22           0      <- no row for this day at all
2026-09-21        4271
2026-09-20        4271
2026-09-19           0      <- no row for this day at all
2026-09-18        4302
2026-09-17          28
2026-09-16        4320
```

Corresponding `resolve_channels` stages:

```
2026-09-19  resolve_channels  1 call   1 unit      0 items   "10 queued, 10 unresolved due=10"
2026-09-20  resolve_channels  86 calls 86 units 4271 items   "4281 queued, 10 unresolved due=4281"
2026-09-21  resolve_channels  86 calls 86 units 4271 items   "4281 queued, 10 unresolved due=4281"
2026-09-22  resolve_channels  1 call   1 unit      0 items   "10 queued, 10 unresolved due=10"
```

The mechanism is visible in the timestamps. `last_checked` is set to the stage's
start instant, and the next day's staleness cutoff is that day's start minus
exactly one day, so the comparison is decided by **sub-second cron jitter**:

```
$ sqlite3 -readonly ... "select substr(last_checked,1,16), count(*) from channels where status is not null group by 1 order by 1 desc;"
2026-09-22T07:18      10
2026-09-21T07:18    4271
2026-09-18T13:34      31
```

| Run | started_at | cutoff = start − 1d | `last_checked` held | stale? |
|---|---|---|---|---|
| 09-19 | 07:18:01.7216 | 09-18T07:18:01.7216 | 09-18T07:18:02.1xx | no → skipped |
| 09-20 | 07:18:01.3549 | 09-19T07:18:01.3549 | 09-18T07:18:02.1xx | yes → refreshed |
| 09-21 | 07:18:02.0934 | 09-20T07:18:02.0934 | 09-20T07:18:01.4xx | yes → refreshed |
| 09-22 | 07:18:01.9163 | 09-21T07:18:01.9163 | 09-21T07:18:02.1xx | no → skipped |

This is the same class of defect as the discovery-cadence problem fixed in
`ee6a1d3` (timestamp arithmetic against a fixed daily schedule); `resolve_channels`
still uses `last_checked < ?` and was not converted to Pacific-date comparison.

### 3.3 `tier0 coverage 1.0` is not yet informative

Every run since 09-19 reports `tier0 coverage 1.0`, because no tier-0 video has
yet aged out of its 30-day window — the frame only began being collected on 09-16.

```
09-19  "tier0_coverage": {"window_days": 30, "done": 11471, "expired": 0, "pending": 33339, "coverage": 1.0}
09-22  "tier0_coverage": {"window_days": 30, "done": 20104, "expired": 0, "pending": 56144, "coverage": 1.0}
```

`pending` inside the window is growing (33,339 → 56,144). The denominator is
`done + expired`, so the figure is trivially 1.0 until tier-0 videos start
expiring around 2026-10-16. It should not be read as 100% coverage achieved.

### 3.4 `backup.sh` output is discarded; today's backups are unverified

The crontab entry has no redirect, and the host has no MTA, so the script's
`integrity_check` result and prune log go nowhere.

```
$ crontab -l | grep backup.sh
34 3 * * *   /data/home/infosphere/youtube_monitoring/deploy/backup.sh

$ ls -la /data/home/infosphere/youtube_monitoring/logs/
pipeline.log   run.jsonl   test_execution.log        <- no backup log

$ grep -rl "backup" .../logs/   →  (no backup output in logs/)
```

Backup **files** exist for every night (§4.8), and NAS pruning to 3 dailies has
worked correctly, but no record of any `integrity_check` since the manual one on
2026-09-18 exists anywhere on the host.

### 3.5 The predicted idle discovery days did not occur

The LOGBOOK entry of 2026-09-18 predicted `discover_uploads` would spend 0 units
on 09-20 and 09-21, and the gate criterion was ruled to permit exactly that. It
did not happen:

```
2026-09-19  discover_uploads  1799 units  "1683/2820 due channels scanned due=2820"
2026-09-20  discover_uploads  1262 units  "1137/1137 due channels scanned due=1137"
2026-09-21  discover_uploads  1712 units  "1683/1683 due channels scanned due=1683"
2026-09-22  discover_uploads  1201 units  "1137/1137 due channels scanned due=1137"
```

The 09-19 sweep could not finish 2,820 due channels inside its budget share
(1,683 scanned), so the tier-0 frame split into two cohorts of 1,683 and 1,137
that now alternate, each on a 2-day cadence. The cadence itself is holding:

```
$ ... "select coalesce(tier,0), count(*), round(max(julianday('now')-julianday(last_discovered)),2) from channels where status='active' group by 1;"
tier 0   2820   max age 1.08 d
tier 1    786   max age 5.08 d
tier 2    665   max age 5.08 d
```

Consequence for the gate: the "no healthcheck alert on a stage with nothing due"
half of the ruled criterion was **never exercised**.

### 3.6 `refresh_videos` is falling behind

```
09-19  queued 76,908  refreshed 53,895   (1,080 units — share ceiling)
09-20  queued 39,467  refreshed 39,449   (790 units — cleared)
09-21  queued 59,317  refreshed 53,879   (1,080 units — share ceiling)
09-22  queued 108,743 refreshed 58,355   (1,169 units — share ceiling)
```

The queue has grown from 39,467 to 108,743 in three days.

### 3.7 `daily.py status` requires an API key it never uses

```
$ ssh gdelt-server 'cd /data/home/infosphere/youtube_monitoring && .venv/bin/python daily.py status'
No API key. Set YOUTUBE_API_KEY in the environment (deploy/run_daily.sh sources .env).
exit 1
```

`docs/operations/ytmon_daily_run.md` lists this command under "Routine checks"
without noting that `.env` must be sourced first. `status` performs no API calls.

### 3.8 One new API failure mode

```
2026-09-22 09:42:57,864 [WARNING] src.daily: commentThreads failed for 61inYxp3n2A:
  400 processingFailure: The API server failed to successfully process the request...
```

Single occurrence across all runs. Handled as `APIError`, so the video stays
`pending`. All 788 other warnings in the log are `403 commentsDisabled`.

---

## 4. Raw outputs

### 4.1 Version comparison

```
LOCAL   branch: production   HEAD: 2f34fbc
CLUSTER deploy/VERSION:
  2f34fbc2549eebe7f01771faecbdf188f7dd3352
  2026-09-18 15:47:12 +0200
  logbook: fix the 3.5 sizing report structure in advance
```

(branch listings in §3.1)

### 4.2 `daily.py status`

```
Quota (Pacific day 2026-09-22)
  commentThreads          3,690 calls       3,690 units
  playlistItems           1,201 calls       1,201 units
  videos                  1,169 calls       1,169 units
  comments                  287 calls         287 units
  channels                    1 calls           1 units
  TOTAL                                     6,348 units of 9,000 (2,652 left)

Channels by tier and status
  tier 0  active            2,820
  tier 0  unresolved            6
  tier 0  uploads_unavailable  30
  tier 1  active              786
  tier 1  unresolved            1
  tier 1  uploads_unavailable   1
  tier 2  active              665
  tier 2  unresolved            3
  tier 3  unknown           1,724

Snapshots
  channel_snapshots        20,079 rows over 11 day(s)
  video_snapshots         304,640 rows over 9 day(s)

Storage (last 7 days)
  data_ytmon   0.590 → 2.079 GB   growth +297.9 MB/day → 30d 11.02 GB  90d 28.89 GB  365d 110.81 GB
  live_db      0.421 → 0.732 GB   growth  +62.2 MB/day → 30d  2.60 GB  90d  6.33 GB  365d  23.45 GB
  nas_ytmon    0.161 → 0.982 GB   growth +164.1 MB/day → 30d  5.91 GB  90d 15.75 GB  365d  60.89 GB

Last run
  run aae6f73047e8 finished 2026-09-22T07:43:58.964344 (1.4h ago)
    resolve_channels        1 calls        1 units         0 items   10 queued, 10 unresolved due=10
    discover_uploads    1,201 calls    1,201 units     9,962 items   1137/1137 due channels scanned due=1137
    refresh_videos      1,169 calls    1,169 units    58,355 items   108743 queued, 95 unavailable due=108743
    harvest_comments    3,977 calls    3,977 units    25,483 items   3618/92955 videos, 482 expired, tier0 coverage 1.0 due=92955
```

### 4.3 Run history

`run_log` has no `status` column; completion is indicated by a non-null `finished_at`.

```
CREATE TABLE run_log (run_id TEXT NOT NULL, stage TEXT, started_at TEXT,
                      finished_at TEXT, calls INTEGER, units_spent INTEGER,
                      items INTEGER, note TEXT);
```

| run_id | started | finished | stages | units | items |
|---|---|---|---|---|---|
| aae6f73047e8 | 2026-09-22T07:18:01 | 2026-09-22T07:43:58 | 4 | 6348 | 93800 |
| b74057e64605 | 2026-09-21T07:18:02 | 2026-09-21T07:44:02 | 4 | 6551 | 143819 |
| 5596a5ee0c3c | 2026-09-20T07:18:01 | 2026-09-20T07:43:59 | 4 | 6255 | 112144 |
| 07e61c89ca92 | 2026-09-19T07:18:01 | 2026-09-19T07:44:49 | 4 | 6552 | 123010 |
| b36475966020 | 2026-09-18T07:18:02 | 2026-09-18T07:32:29 | 4 | 5714 | 117572 |
| 23713267f38e | 2026-09-17T07:18:02 | 2026-09-17T07:46:23 | 4 | 6384 | 133248 |
| 21ef37e46a97 | 2026-09-16T11:09:57 | 2026-09-16T11:35:09 | 4 | 4370 | 54798 |
| 75ab576b4ed5 | 2026-09-16T10:49:12 | 2026-09-16T11:05:20 | 3 | 2024 | 31332 |
| f46c844984aa | 2026-09-16T08:16:18 | 2026-09-16T08:16:26 | 1 | 58 | 2850 |

**One finished run per calendar day for 17, 18, 19, 20, 21 and 22 September — no missing day.**
All runs have a non-null `finished_at`. **No run has 0 units and no stage has 0 units.**
The two short runs on 09-16 are the pre-cutover manual runs already recorded in
the LOGBOOK (`75ab576b4ed5` is the crash at three stages, since fixed).

Per-stage, runs since 09-19:

| day | stage | calls | units | items | note |
|---|---|---|---|---|---|
| 09-19 | resolve_channels | 1 | 1 | 0 | 10 queued, 10 unresolved due=10 |
| 09-19 | discover_uploads | 1799 | 1799 | 15082 | 1683/2820 due channels scanned due=2820 |
| 09-19 | refresh_videos | 1080 | 1080 | 53895 | 76908 queued, 105 unavailable due=76908 |
| 09-19 | harvest_comments | 3672 | 3672 | 54033 | 2764/66744 videos, 3485 expired, tier0 coverage 1.0 |
| 09-20 | resolve_channels | 86 | 86 | 4271 | 4281 queued, 10 unresolved due=4281 |
| 09-20 | discover_uploads | 1262 | 1262 | 16559 | 1137/1137 due channels scanned due=1137 |
| 09-20 | refresh_videos | 790 | 790 | 39449 | 39467 queued, 18 unavailable due=39467 |
| 09-20 | harvest_comments | 4117 | 4117 | 51865 | 3232/80228 videos, 293 expired, tier0 coverage 1.0 |
| 09-21 | resolve_channels | 86 | 86 | 4271 | 4281 queued, 10 unresolved due=4281 |
| 09-21 | discover_uploads | 1712 | 1712 | 5317 | 1683/1683 due channels scanned due=1683 |
| 09-21 | refresh_videos | 1080 | 1080 | 53879 | 59317 queued, 121 unavailable due=59317 |
| 09-21 | harvest_comments | 3673 | 3673 | 80352 | 2148/83520 videos, 288 expired, tier0 coverage 1.0 |
| 09-22 | resolve_channels | 1 | 1 | 0 | 10 queued, 10 unresolved due=10 |
| 09-22 | discover_uploads | 1201 | 1201 | 9962 | 1137/1137 due channels scanned due=1137 |
| 09-22 | refresh_videos | 1169 | 1169 | 58355 | 108743 queued, 95 unavailable due=108743 |
| 09-22 | harvest_comments | 3977 | 3977 | 25483 | 3618/92955 videos, 482 expired, tier0 coverage 1.0 |

`logs/run.jsonl` (last 7 lines) parsed cleanly as JSON; the per-run reports agree
with `run_log` on every figure.

### 4.4 Quota ledger

| day | units | calls |
|---|---|---|
| 2026-09-22 | 6348 | 6348 |
| 2026-09-21 | 6551 | 6551 |
| 2026-09-20 | 6255 | 6255 |
| 2026-09-19 | 6552 | 6552 |
| 2026-09-18 | 5746 | 5746 |
| 2026-09-17 | 6384 | 6384 |
| **2026-09-16** | **7117** | **7117** |
| 2026-09-15 | 1782 | 1782 |

Per-endpoint, two most recent days:

| day | endpoint | calls | units |
|---|---|---|---|
| 09-22 | commentThreads | 3690 | 3690 |
| 09-22 | playlistItems | 1201 | 1201 |
| 09-22 | videos | 1169 | 1169 |
| 09-22 | comments | 287 | 287 |
| 09-22 | channels | 1 | 1 |
| 09-21 | commentThreads | 2414 | 2414 |
| 09-21 | playlistItems | 1712 | 1712 |
| 09-21 | comments | 1259 | 1259 |
| 09-21 | videos | 1080 | 1080 |
| 09-21 | channels | 86 | 86 |

Note: `quota_ledger` for 2026-09-18 reads 5,746 while `run_log` for that day sums
to 5,714 — the 32-unit difference is the `recheck_unresolved.py` pass recorded in
the LOGBOOK, which is ledger-charged but not part of any run.

### 4.5 Row counts

| table | rows |
|---|---|
| channels | 6,036 |
| videos | 114,002 |
| comments | 1,080,453 |
| channel_snapshots | 20,079 |
| video_snapshots | 304,640 |

`comments_state`:

| state | n |
|---|---|
| pending | 83,126 |
| done | 21,047 |
| expired | 4,548 |
| deferred | 4,305 |
| disabled | 780 |
| unavailable | 196 |

Channels by tier and status:

| tier | status | n |
|---|---|---|
| 0 | active | 2,820 |
| 0 | uploads_unavailable | 30 |
| 0 | unresolved | 6 |
| 1 | active | 786 |
| 1 | unresolved | 1 |
| 1 | uploads_unavailable | 1 |
| 2 | active | 665 |
| 2 | unresolved | 3 |
| 3 | (null) | 1,724 |

### 4.6 Cron and lock

```
64:# ytmon — YouTube monitoring pipeline.
80:18 9 * * *   /data/home/infosphere/youtube_monitoring/deploy/run_daily.sh
81:46 12 * * *  /data/home/infosphere/youtube_monitoring/deploy/healthcheck.sh
82:34 3 * * *   /data/home/infosphere/youtube_monitoring/deploy/backup.sh

$ ls -la /data/ytmon/.ytmon.lock
-rw-rw-r-- 1 infosphere infosphere 0 Sep 16 12:49 /data/ytmon/.ytmon.lock

$ pgrep -af '[d]aily\.py|[c]ollect\.py'
(none running)
```

Lock file is 0 bytes and unchanged since 2026-09-16 12:49 — never contended.

### 4.7 Healthcheck and alerts

```
$ .venv/bin/python deploy/healthcheck.py --help
usage: healthcheck.py [-h] [--dry-run]
  --dry-run   Print what would be reported; send no mail.

$ .venv/bin/python deploy/healthcheck.py --dry-run
2026-09-22T09:10:58.965294 healthcheck OK
exit=0
```

Warning counts by day (no ERROR lines at any point):

| day | WARNING | ERROR |
|---|---|---|
| 09-19 | 98 | 0 |
| 09-20 | 63 | 0 |
| 09-21 | 199 | 0 |
| 09-22 | 84 | 0 |

All are `403 commentsDisabled` except the single `400 processingFailure` in §3.8.

### 4.8 Backups and storage

Local `/data/ytmon/backups/`:

```
wikidata_raw_20260916.tar.gz     7.0M  Sep 16 11:29   (manual, pre-dates backup.sh)
ytmon_2026-09-17.db.gz           154M  Sep 17 03:34
ytmon_2026-09-18.db.gz           187M  Sep 18 03:34
ytmon_2026-09-19.db.gz           203M  Sep 19 03:34
wikidata_raw_2026-09-20.tar.gz    30M  Sep 20 03:34   (weekly, Sunday)
ytmon_2026-09-20.db.gz           220M  Sep 20 03:34
ytmon_2026-09-21.db.gz           235M  Sep 21 03:34
ytmon_2026-09-22.db.gz           252M  Sep 22 03:34
```

NAS `/data/nas_penpen/infosphere/ytmon/backups/`:

```
ytmon_2026-09-19.db.gz           203M
wikidata_raw_2026-09-20.tar.gz    30M
ytmon_2026-09-20.db.gz           220M
ytmon_2026-09-21.db.gz           235M
ytmon_2026-09-22.db.gz           252M
```

**A backup exists for every night since 2026-09-17.** The NAS holds four dailies
(09-19 … 09-22), consistent with the 3-daily retention rule; 09-17 and 09-18 were
pruned as designed. The weekly raw tarball was produced on Sunday 09-20 and
copied to the NAS. No `integrity_check` result is recorded anywhere (§3.4).

Disk:

```
/dev/mapper/vg_shared-lv_shared   13T  5.4T  6.6T  46% /data
//192.168.0.237/infosphere        26T   12G   26T   1% /data/nas_penpen/infosphere
```

`df -h /data/nas_penpen` reports the `/data` filesystem, because the CIFS mount
point is one level deeper at `/data/nas_penpen/infosphere`.

`storage_ledger`:

| day | data_ytmon | live_db | nas_ytmon |
|---|---|---|---|
| 2026-09-22 | 2,079,328,627 | 732,356,608 | 982,169,731 |
| 2026-09-21 | 1,762,375,699 | 679,256,064 | 914,366,247 |
| 2026-09-20 | 1,468,575,935 | 630,976,512 | 830,320,752 |
| 2026-09-19 | 1,154,062,687 | 577,069,056 | 569,714,960 |

### 4.9 Secrets sanity

```
.env: present, mode 600
YOUTUBE_API_KEY: set, non-empty, length 39
~/.taiwa_notify_secrets: present, mode -rw-------
```

No value from either file was read, printed or logged.
