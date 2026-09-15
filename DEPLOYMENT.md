# Deployment Guide

## Branch Strategy

This repository uses a two-branch workflow:

### `main` - Development Branch
- **Purpose**: Active development and testing
- **Use for**:
  - New features
  - Bug fixes
  - Experiments
  - Testing with limited data
- **Stability**: May contain work-in-progress code
- **Deploy to**: Local development machines

### `production` - Deployment Branch
- **Purpose**: Stable, production-ready code
- **Use for**:
  - Deployment to remote in-house server
  - Long-running data collection
  - Stable releases
- **Stability**: Only merged after thorough testing
- **Deploy to**: Remote in-house server

## Workflow

### During Development
```bash
# Work on main branch
git checkout main

# Make changes, test locally
python collect.py --sources data/sources.csv --max-channels 3

# Commit changes
git add .
git commit -m "Description of changes"
git push origin main
```

### Promoting to Production
When code is ready for deployment:

```bash
# 1. Ensure main branch is stable and tested
git checkout main
git pull origin main

# 2. Merge main into production
git checkout production
git pull origin production
git merge main

# 3. Test the production branch
python test_api_quick.py
python collect.py --sources data/sources.csv --max-channels 3

# 4. Push to production branch
git push origin production
```

## Server Deployment

### Initial Setup on Remote Server
```bash
# Clone repository
git clone https://github.com/losardor/youtube-monitorin-pipeline.git
cd youtube-monitorin-pipeline

# Checkout production branch
git checkout production

# Setup environment
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure API keys
cp config/config_comprehensive.yaml.template config/config_comprehensive.yaml
# Edit config_comprehensive.yaml with production API key

# Create data directories
mkdir -p data/raw data/processed data/checkpoints logs

# Test connection
python test_api_quick.py
```

### Updating Production Server
```bash
# On the remote server
cd youtube-monitorin-pipeline
source venv/bin/activate

# Pull latest production code
git checkout production
git pull origin production

# Restart collection if needed
python collect.py --sources data/sources.csv --resume
```

## Production Checklist

Before merging to production:

- [ ] All tests pass locally
- [ ] API connection verified with `test_api_quick.py`
- [ ] Tested with limited channels using `python collect.py --max-channels 3`
- [ ] No API keys or sensitive data in code
- [ ] Configuration templates updated if needed
- [ ] Documentation updated (README, CLAUDE.md)
- [ ] Checkpoint/resume functionality tested
- [ ] Error handling tested with failed channels

## Rollback Procedure

If production deployment fails:

```bash
# On server, revert to previous commit
git checkout production
git log --oneline  # Find previous stable commit
git reset --hard <previous-commit-hash>

# Or reset to match remote
git reset --hard origin/production
```

## Monitoring Production

```bash
# Check collection progress
python view_data.py --stats

# Monitor logs in real-time
tail -f logs/pipeline.log

# Check for errors
grep -i error logs/pipeline.log | tail -50

# Database size
du -h data/youtube_monitoring.db
```

## Automation on Production Server

Consider setting up:

1. **Auto-resume on failure**:

The backfill and the daily monitoring run write the same SQLite file. WAL mode
allows only one writer at a time, so both take the same advisory lock on
`data/.ytmon.lock` — `flock(1)` here and `fcntl.flock` inside the Python. The
paths must match or the two will not contend.

```bash
# Add to crontab
# Backfill: hourly, during the day only, never overlapping the 09:17 daily slot.
# flock -n exits immediately (status 1) if the daily run holds the lock, rather
# than queueing a multi-hour job behind it.
17 10-23 * * * cd /path/to/youtube-monitorin-pipeline && flock -n data/.ytmon.lock ./venv/bin/python collect.py --sources data/sources.csv --resume >> logs/cron.log 2>&1
```

The old entry was `*/30 * * * *` with no lock. Two problems it had: every other
invocation could collide with the 09:17 daily run and corrupt nothing but lose
one of the two runs' work, and a half-hour cadence started a new backfill while
the previous one was still going. Both are fixed by the lock plus the hourly,
daytime-only window.

The daily monitoring run owns the 09:17 slot (see
`docs/operations/ytmon_daily_run.md`, phase 3):

```cron
CRON_TZ=Europe/Rome
17 9 * * *   /path/to/youtube-monitorin-pipeline/deploy/run_daily.sh
```

Quota resets at midnight US/Pacific, which is 09:00 in Rome under both DST
regimes. The daily run holds the lock for minutes; the backfill window opens an
hour later.

2. **Daily statistics report**:
```bash
# Add to crontab
0 8 * * * cd /path/to/youtube-monitorin-pipeline && source venv/bin/activate && python view_data.py --stats >> logs/daily_stats.log
```

3. **Disk space monitoring**:
```bash
# Add to crontab
0 */6 * * * df -h /path/to/youtube-monitorin-pipeline/data >> logs/disk_usage.log
```

## Configuration Differences

### Development (main branch)
- Uses `config/config.yaml`
- Limited collection (50 videos, 100 comments)
- 10K quota limit
- Suitable for testing

### Production (production branch)
- Uses `config/config_comprehensive.yaml`
- Unlimited collection (all videos, all comments)
- 1M quota limit (requires Google approval)
- Full-scale data collection

## Security Notes

### On Production Server:
1. Restrict file permissions:
```bash
chmod 600 config/config_comprehensive.yaml
chmod 700 data/
```

2. Use separate API key from development

3. Regular backups:
```bash
# Backup database daily
cp data/youtube_monitoring.db backups/youtube_monitoring_$(date +%Y%m%d).db
```

4. Monitor API quota usage to avoid unexpected charges

## Support

For issues during deployment:
- Check `logs/pipeline.log` for errors
- Verify API key in configuration
- Ensure sufficient disk space (100GB+ recommended)
- Check network connectivity to YouTube API
- Review GitHub issues or contact maintainer
