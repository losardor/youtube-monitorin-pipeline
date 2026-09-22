#!/usr/bin/env bash
# Nightly ytmon backup, 03:34 Europe/Rome.
#
#   - sqlite3 .backup of the live database (consistent under WAL), gzipped
#   - weekly tar of data/raw/ (Sundays): the archived API responses, which
#     represent quota already spent and are cheap to keep
#   - copy to the NAS, then prune both locations on their own schedules
#   - record sizes in storage_ledger so growth is watched rather than assumed
set -euo pipefail

ROOT=/data/home/infosphere/youtube_monitoring
DB=/data/ytmon/youtube_monitoring.db
LOCAL=/data/ytmon/backups
NAS=/data/nas_penpen/infosphere/ytmon/backups
DAY=$(date -u +%F)
DOW=$(date -u +%u)          # 7 = Sunday

cd "$ROOT"
mkdir -p "$LOCAL"
log() { echo "$(date -u +%FT%TZ) [backup] $*"; }

# ---- database ------------------------------------------------------------
OUT="$LOCAL/ytmon_${DAY}.db"
log "backing up $DB -> $OUT"
sqlite3 "$DB" ".backup '$OUT'"

# Printed verbatim and on its own line: deploy/healthcheck.py parses the most
# recent "integrity_check:" line out of logs/backup.log, so the wording here is
# an interface, not a message.
INTEGRITY=$(sqlite3 "$OUT" 'PRAGMA integrity_check;' | head -1)
log "integrity_check: $INTEGRITY"
if [ "$INTEGRITY" != "ok" ]; then
  log "FATAL: integrity_check did not return ok for $OUT"
  exit 1
fi
gzip -f "$OUT"
log "wrote ${OUT}.gz ($(du -h "${OUT}.gz" | cut -f1))"

# ---- weekly raw archive --------------------------------------------------
if [ "$DOW" = "7" ]; then
  RAW="$LOCAL/wikidata_raw_${DAY}.tar.gz"
  log "weekly raw archive -> $RAW"
  tar -czf "$RAW" -C data raw
  log "wrote $RAW ($(du -h "$RAW" | cut -f1))"
fi

# ---- copy to the NAS -----------------------------------------------------
if mkdir -p "$NAS" 2>/dev/null; then
  cp -f "${OUT}.gz" "$NAS/" && log "copied $(basename "${OUT}.gz") to NAS"
  [ "$DOW" = "7" ] && cp -f "$LOCAL/wikidata_raw_${DAY}.tar.gz" "$NAS/" \
    && log "copied weekly raw archive to NAS"
else
  log "WARNING: NAS path $NAS unavailable; local copy only"
fi

# ---- prune ---------------------------------------------------------------
# Local: keep 14 daily database backups, nothing else.
log "pruning local (keep 14 daily db backups)"
ls -1t "$LOCAL"/ytmon_*.db.gz 2>/dev/null | tail -n +15 | while read -r f; do
  log "  removing local $(basename "$f")"; rm -f "$f"
done

# NAS: 3 daily, then one per week for 8 weeks, then one per month forever.
# Narrowed from 14 daily on 2026-09-18: a full database backup is ~190 MB and
# grows daily, so 14 dailies on a shared NAS is several GB of near-duplicates
# for little recovery value. Three days covers the realistic 'yesterday was
# wrong' case; the weekly and monthly tiers cover everything older.
# Raw tarballs are kept indefinitely -- they are small and represent quota spent.
if [ -d "$NAS" ]; then
  log "pruning NAS (3 daily, 8 weekly, then monthly; raw kept forever)"
  python3 - "$NAS" <<'PYEOF' | while read -r line; do log "  $line"; done
import os, re, sys
from datetime import date, timedelta
nas = sys.argv[1]
pat = re.compile(r'^ytmon_(\d{4}-\d{2}-\d{2})\.db\.gz$')
files = {}
for name in os.listdir(nas):
    m = pat.match(name)
    if m:
        files[date.fromisoformat(m.group(1))] = name
if not files:
    sys.exit(0)
today = max(files)
keep = set()
for d in files:
    age = (today - d).days
    if age <= 3:
        keep.add(d)                      # the last three days
    elif age <= 3 + 56:
        if d.weekday() == 6:
            keep.add(d)                  # one per week (Sundays) for 8 weeks
    elif d.day == 1:
        keep.add(d)                      # one per month, indefinitely
for d in sorted(set(files) - keep):
    os.remove(os.path.join(nas, files[d]))
    print(f"removing NAS {files[d]}")
PYEOF
fi

# ---- storage ledger ------------------------------------------------------
# Written after every run so growth is a measured series, not an assumption.
db_bytes=$(stat -c %s "$DB")
local_bytes=$(du -sb /data/ytmon 2>/dev/null | cut -f1)
nas_bytes=$(du -sb /data/nas_penpen/infosphere/ytmon 2>/dev/null | cut -f1 || echo 0)
sqlite3 "$DB" <<SQL
CREATE TABLE IF NOT EXISTS storage_ledger (
    day      TEXT NOT NULL,
    location TEXT NOT NULL,
    bytes    INTEGER,
    PRIMARY KEY (day, location)
);
INSERT INTO storage_ledger (day, location, bytes) VALUES
  ('$DAY', 'live_db',   $db_bytes),
  ('$DAY', 'data_ytmon', ${local_bytes:-0}),
  ('$DAY', 'nas_ytmon',  ${nas_bytes:-0})
ON CONFLICT(day, location) DO UPDATE SET bytes = excluded.bytes;
SQL
log "storage_ledger: live_db=${db_bytes} data_ytmon=${local_bytes:-0} nas_ytmon=${nas_bytes:-0}"
log "done"
