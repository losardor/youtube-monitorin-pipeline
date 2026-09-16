#!/usr/bin/env bash
# Daily ytmon run. Installed on gdelt-server, invoked from the infosphere
# crontab at 09:18 Europe/Rome (quota resets at midnight US/Pacific, which is
# 09:00 Rome under both DST regimes).
#
# flock -n makes a run that collides with a backfill exit immediately with
# status 1 rather than queue behind a multi-hour job; healthcheck.sh reports it.
set -euo pipefail

ROOT=/data/home/infosphere/youtube_monitoring
cd "$ROOT"

if [ ! -f ./.env ]; then
  echo "$(date -u +%FT%TZ) FATAL: $ROOT/.env missing; refusing to run" >&2
  exit 78          # EX_CONFIG
fi
set -a; . ./.env; set +a

if [ -z "${YOUTUBE_API_KEY:-}" ]; then
  echo "$(date -u +%FT%TZ) FATAL: YOUTUBE_API_KEY unset in .env" >&2
  exit 78
fi

mkdir -p logs
exec flock -n /data/ytmon/.ytmon.lock \
  .venv/bin/python daily.py run --config config/config_daily.yaml \
  >> logs/run.jsonl 2>> logs/pipeline.log
