# ytmon daily run — operations

Deployment of the YouTube monitoring pipeline on `infosphereVM`.
Supersedes `SERVER_MIGRATION_GUIDE.md`.

## Host and layout

| | |
|---|---|
| Host | `infosphereVM`, SSH alias `gdelt-server`, user `infosphere` |
| OS | Ubuntu 24.04.4 LTS, kernel 6.8.0 |
| Code | `/data/home/infosphere/youtube_monitoring/` (rsync from the local `production` checkout) |
| Venv | `/data/home/infosphere/youtube_monitoring/.venv` |
| Database | `/data/ytmon/youtube_monitoring.db` (local LVM — **not** the CIFS NAS) |
| Lock | `/data/ytmon/.ytmon.lock` |
| Local backups | `/data/ytmon/backups/` |
| NAS backups | `/data/nas_penpen/infosphere/ytmon/backups/` |
| Secrets | `/data/home/infosphere/youtube_monitoring/.env`, mode 600 |
| Logs | `logs/run.jsonl` (one JSON report per run), `logs/pipeline.log` |

## Interpreter: Python 3.12

**Deployed: 3.12.3. Local development: 3.10.12.**

The brief specified 3.10, which is present on the host but **cannot build a
usable venv**: `python3.10 -m venv` produces a tree with no `pip`, because
`ensurepip` raises `ModuleNotFoundError`. The installed `python3.10-venv` is
`3.10.12-1~22.04.15` — a **jammy** package on a **noble** system — and there is
no passwordless sudo to repair it.

`python3.12 -m venv` works cleanly (pip 24.0), the full `requirements.txt`
installs, and every runtime import succeeds. The code is version-neutral here:
`zoneinfo` is 3.9+, and every module using `X | None` annotations carries
`from __future__ import annotations`.

Always invoke the venv interpreter by absolute path — the box has a 3.10/3.12
split and `python3` is 3.12.

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q        # deployment gate: must be green
```

## Database is on local disk, deliberately

SQLite in WAL mode requires a filesystem with working POSIX locking. The
CIFS-mounted NAS shares (`/data/nas_penpen`, `/data/nas`) are **not** valid
locations for the live database — only for backups of it.

## Schedule

The crontab on this host is shared with TAIWA and GDELT. **ytmon appends three
lines and touches nothing else.** Minutes are chosen to clear every existing
job:

| Existing | Schedule |
|---|---|
| TAIWA `run_live.sh` | `*/15` — :00 :15 :30 :45 |
| `gdelt_update.sh` | every 5 min — :02 … :57 |
| `gdelt_reconcile.sh` | :40 |
| `gdelt_reprobe.py` | :50 |
| `drain_watchdog.sh` | every 10 min — :03 … :53 |

```cron
CRON_TZ=Europe/Rome
18 9 * * *   .../deploy/run_daily.sh
46 12 * * *  .../deploy/healthcheck.sh
34 3 * * *   .../deploy/backup.sh
```

The brief's 09:17 / 12:45 / 03:30 all collided (`:17` with `gdelt_update`,
`:45` and `:30` with TAIWA). Crontab is used rather than a systemd user timer
because these are short oneshots with no ordering dependencies — and because
the host's other jobs already live there, so one place shows the whole picture.

**DST caveat.** Quota resets at midnight US/Pacific, which is 09:00 Rome under
both regimes. The zones shift within a couple of weeks of each other; on those
days the run starts up to an hour early or late. This is harmless: the ledger
is keyed by Pacific day, so the governor always bills the right day.

## Secrets

`.env` holds `YOUTUBE_API_KEY` and must use a **dedicated Cloud project key**.
Sharing a key with the backfill or with ad-hoc queries means one can exhaust
the other's quota, and the ledger would stop describing what the daily run
actually had available. `run_daily.sh` exits 78 (`EX_CONFIG`) if `.env` is
missing or the key is unset, rather than running against no key.

### The daily project is separate from the quota-request project, by design

Quota is granted **per Cloud project**, not per key. The 1M increase is being
requested against one project; the daily monitor deliberately runs on a
*different* one. That keeps the two from drawing on the same bucket while the
request is pending, so neither the backfill nor an ad-hoc query can starve the
daily series, and `quota_ledger` continues to describe what the daily run
actually had available.

**When the 1M approval lands**, `.env` switches to the approved project's key
and `quota.daily_budget` in `config/config_daily.yaml` is raised to match.

That switch is a **LOGBOOK event**, and it must record the **Pacific day it
took effect** — the ledger is keyed by Pacific billing day, and the effective
`daily_budget` changes partway through the series. Without that date, any later
analysis of spend against budget silently compares two different ceilings.

Alert credentials come from `~/.taiwa_notify_secrets` (mode 600), shared with
the GDELT jobs: `TAIWA_SMTP_USER`, `TAIWA_SMTP_APP_PASSWORD`, `TAIWA_ALERT_TO`.

## Alerting

`deploy/notify.py` is a **vendored copy** of
`gdelt_dagster/gdelt_dagster/notify.py` (md5 in its header), not an import:
ytmon should not depend on another project's tree staying put, and a change
there must not alter ytmon's alerting silently.

Subjects are prefixed `[ytmon]`; `thread_key` is `ytmon-<pacific day>`, so a
day's alerts group into one mail thread.

## Backups and retention

`backup.sh` runs nightly at 03:34 and **logs to `logs/backup.log`** (the
crontab entry redirects into it; the host has no MTA, so without that redirect
the verdict is discarded). It prints `integrity_check: <result>` verbatim and
exits non-zero on anything other than `ok`; `healthcheck.py` parses the most
recent such line and alerts if it is missing, older than 36 hours, or not `ok`.

Steps:

1. `sqlite3 .backup` of the live database, `integrity_check`, gzip.
2. Sundays: `tar -czf` of `data/raw/` — the archived API responses.
3. Copy both to the NAS.
4. Prune, logging every removal.
5. Write `storage_ledger`.

| Location | Retention |
|---|---|
| `/data/ytmon/backups/` | 14 daily database backups |
| NAS `ytmon/backups/` | 3 daily, then weekly for 8 weeks, then monthly indefinitely |
| NAS raw tarballs | indefinitely — small, and they represent quota already spent |

### The NAS is a shared resource

`//192.168.0.237/infosphere` is not ours alone. Usage under `ytmon/` is
**measured, not assumed**: `storage_ledger` records three figures every night
(live database, `/data/ytmon` total, NAS `ytmon/` total), `daily.py status`
prints the last 7 days with day-over-day deltas and a linear projection to 30,
90 and 365 days, and the healthcheck alerts if NAS usage grows more than 25%
in a single day — which is what a runaway backfill looks like before it fills
the share.

**Report the growth figure to the share's owner once it is stable**, i.e. after
a couple of weeks of ordinary runs, so the projection reflects the steady state
rather than the initial load.

## `quota.charge_error_responses`

The API answers some requests with an error it still served: `400`, `403` other
than `quotaExceeded`/`dailyLimitExceeded`, and `404`. Whether Google bills those
is not documented, and the one day available to settle it — 2026-09-16 — could
not, because the console read *below* the ledger.

`quota_ledger.error_calls` therefore **counts** them per endpoint per Pacific
day, always. `quota.charge_error_responses` (default **false**) decides whether
they are also **charged** against the budget.

| Flag | `units` column | Compare against the console |
|---|---|---|
| `false` (current) | 200 responses only | `units + error_calls` |
| `true` | 200s and served errors | `units` |

`daily.py status` prints both columns and their sum for the last 7 Pacific days.

**Flipping this flag is a LOGBOOK event and must record the Pacific day it took
effect**, because the day's budget arithmetic changes from that day on and any
later comparison of spend against budget would otherwise span two rules without
saying so.

Refusals are never counted or charged: a `quotaExceeded` or rate-limit response
is the API declining to serve, not serving an error.

## Healthcheck

Alerts when any of these holds:

- no `run_log` row finished in the last 36 hours;
- the last run spent 0 units;
- `harvest_comments` logged 0 items while `discover_uploads` logged > 0;
- free space on `/data` under 10 GB;
- NAS usage under `ytmon/` grew more than 25% in a day.

A missing mount is reported, not fatal: a check that dies is indistinguishable
from one that passed.

## Coexistence with the backfill

`daily.py` and `collect.py` write the same file and take the same advisory lock
on `/data/ytmon/.ytmon.lock` — `fcntl.flock` in Python, `flock(1)` in the
wrapper, the same kernel lock on the same inode. `run_daily.sh` uses `flock -n`
so a collision exits 1 immediately rather than queueing behind a multi-hour
backfill; the healthcheck reports the missed run.

## The replica guard

After the cutover the authoritative database is
`gdelt-server:/data/ytmon/youtube_monitoring.db`. The workstation copy is
renamed `youtube_monitoring.replica.db`, and both `daily.py` and `collect.py`
**refuse to open any file whose name contains `replica`** without
`--i-know-this-is-a-replica`.

The guard is on the filename rather than on intent because the failure it
prevents is silent: writing to the replica produces a second divergent history
that looks authoritative.

## Known: `datetime.utcnow()` deprecation

Python 3.12 emits `DeprecationWarning` for `datetime.utcnow()`, which is
scheduled for removal. Eleven call sites still use it directly
(`src/database.py`, `deploy/healthcheck.py`, `daily.py`); `src/daily.py`
already routes through a helper that does not.

The fix is to route every site through that helper, whose body is
`datetime.now(timezone.utc).replace(tzinfo=None)` — the **same naive UTC
value, byte-identical serialisation, no migration**.

**Moving to timezone-aware timestamps is deferred indefinitely** and should not
be done casually. Stored timestamps are naive (`2026-09-16T10:00:00.123456`)
and handled as strings. Ordering is *not* the problem — an ISO offset is
appended after the whole date and time, so for UTC values string order still
tracks time order. **Exact equality is the problem**, and these depend on it:
the snapshot primary keys `(channel_id, observed_at)` and
`(video_id, observed_at)`, the migration's join of a snapshot to its record's
timestamp, and the `INSERT OR IGNORE` that makes re-running idempotent. A value
written naive and looked up aware does not match, and it fails silently — a
duplicate row rather than an error. Any such change needs a migration of every
stored timestamp and its own gate.

## Routine checks

```bash
cd /data/home/infosphere/youtube_monitoring
.venv/bin/python daily.py status                 # quota, tiers, storage, last run
tail -1 logs/run.jsonl | python3 -m json.tool    # last run's report
tail -20 logs/backup.log                         # last backup + integrity_check
sqlite3 -readonly /data/ytmon/youtube_monitoring.db \
  "SELECT day, endpoint, calls, units, error_calls FROM quota_ledger ORDER BY day DESC LIMIT 10;"
.venv/bin/python deploy/healthcheck.py --dry-run  # what it would alert on, sends nothing
```

`status` needs **no API key** — it reads the database and calls nothing, so it
runs without sourcing `.env`. Use `sqlite3 -readonly` for ad-hoc queries so an
inspection can never write to the live database.

`status` prints a 7-day ledger table with `units`, `calls`, `error_calls` and
`units + error_calls`. That last column is the figure to compare against the
Cloud console while `quota.charge_error_responses` is false — see below.
