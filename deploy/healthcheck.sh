#!/usr/bin/env bash
# ytmon healthcheck, 12:46 Europe/Rome. Alerts via the vendored notify.py
# (Gmail SMTP, ~/.taiwa_notify_secrets), one thread per Pacific day.
#
# Alerts when any of these holds:
#   - no run_log row finished in the last 36 hours
#   - the last run spent 0 units
#   - harvest_comments logged 0 items while discover_uploads logged > 0 new videos
#   - free space on /data under 10 GB
#   - NAS usage under ytmon/ grew more than 25% in a day (runaway backfill)
set -euo pipefail

ROOT=/data/home/infosphere/youtube_monitoring
cd "$ROOT"
exec .venv/bin/python deploy/healthcheck.py "$@"
