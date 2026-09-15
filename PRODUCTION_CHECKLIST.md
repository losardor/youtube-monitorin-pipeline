# Production Deployment Checklist

## 📋 Pre-Production Verification

### 1. Environment Setup
- [ ] Python 3.8+ installed
- [ ] Virtual environment created and activated
- [ ] All requirements installed (`pip install -r requirements.txt`)
- [ ] Verify with: `python verify_production.py`

### 2. API Configuration
- [ ] YouTube Data API v3 key obtained from Google Cloud Console
- [ ] API key added to `config/config_comprehensive.yaml`
- [ ] Quota limit verified (1,000,000 units/day for production)
- [ ] Test API connection: `python test_api_quick.py`

### 3. Database Preparation
- [ ] Database structure verified (run `python daily.py status`)
- [ ] `quota_ledger` table exists and records the current Pacific day
- [ ] No data integrity issues (check with SQL queries)
- [ ] Backup existing database if needed

### 4. Source Data
- [ ] `data/sources.csv` file exists with YouTube URLs
- [ ] Column `Youtube` is present with valid URLs
- [ ] Optional metadata columns preserved (Domain, Rating, etc.)
- [ ] Total channel count documented

## 🧪 Testing Phase

### 5. Small-Scale Test (Required)
```bash
# Test with 3-5 channels first
python collect.py --sources data/sources.csv --max-channels 3
```
- [ ] Collection starts successfully
- [ ] Quota tracking shows both session and cumulative
- [ ] Checkpoint file created in `data/checkpoints/`
- [ ] Database records created correctly
- [ ] No errors in `logs/pipeline.log`

### 6. Resume Test (Required)
```bash
# Interrupt test with Ctrl+C, then:
python collect.py --sources data/sources.csv --resume
```
- [ ] Collection resumes from correct channel index
- [ ] Cumulative quota continues from previous value
- [ ] No duplicate data inserted
- [ ] Checkpoint updated correctly

### 7. Monitoring Test
```bash
# In separate terminal:
python monitor_collection.py
```
- [ ] Dashboard displays current statistics
- [ ] Quota progress bar shows correct percentage
- [ ] Processing rates calculated correctly
- [ ] Recent logs displayed

## 🚀 Production Deployment

### 8. Final Pre-Flight Checks
- [ ] Remove any test checkpoints: `rm data/checkpoints/*.json`
- [ ] Clear test data if needed (or keep for continuity)
- [ ] Verify quota buffer set to 50,000 units
- [ ] Document starting quota_cumulative value
- [ ] Set up monitoring terminal

### 9. Start Production Collection

#### Option A: Fresh Start
```bash
python collect.py --sources data/sources.csv
```

#### Option B: Resume from Previous Run
```bash
python collect.py --sources data/sources.csv --resume
```

### 10. Active Monitoring
Run these in separate terminals:

**Terminal 1 - Main Collection:**
```bash
python collect.py --sources data/sources.csv
```

**Terminal 2 - Real-time Monitor:**
```bash
python monitor_collection.py --refresh 5
```

**Terminal 3 - Log Monitoring:**
```bash
tail -f logs/pipeline.log | grep -E "quota|ERROR|WARNING"
```

**Terminal 4 - Database Queries:**
```bash
# Check quota usage
sqlite3 data/youtube_monitoring.db < verify_queries.sql

# Quick quota check
sqlite3 data/youtube_monitoring.db "
  SELECT quota_cumulative,
         ROUND((quota_cumulative/1000000.0)*100, 2) || '%' as used
  FROM collection_runs
  WHERE status='running';"
```

## 📊 Production Monitoring Queries

### Check Current Progress
```sql
sqlite3 data/youtube_monitoring.db "
SELECT
    channels_processed,
    videos_collected,
    comments_collected,
    quota_cumulative,
    ROUND((quota_cumulative/1000000.0)*100, 2) || '%' as quota_used
FROM collection_runs
WHERE status='running';"
```

### Verify Quota Tracking Accuracy
```sql
sqlite3 data/youtube_monitoring.db "
SELECT
    cr.quota_used as reported,
    qt.calculated as calculated,
    ABS(cr.quota_used - qt.calculated) as difference
FROM collection_runs cr
LEFT JOIN (
    SELECT run_id, SUM(quota_cost) as calculated
    FROM quota_tracking
    GROUP BY run_id
) qt ON cr.run_id = qt.run_id
WHERE cr.run_id = (SELECT MAX(run_id) FROM collection_runs);"
```

## 🛑 Quota Management

### Warning Thresholds
- **Green Zone**: 0-800,000 units (80%)
- **Yellow Zone**: 800,000-950,000 units (80-95%)
- **Red Zone**: 950,000+ units (>95%)
- **Auto-Stop**: 950,000 units (with 50K buffer)

### If Approaching Limit
1. Monitor cumulative quota closely
2. Consider interrupting with Ctrl+C
3. Save checkpoint automatically on interrupt
4. Resume next day after quota reset

## 🔧 Troubleshooting

### Common Issues and Solutions

#### API Key Issues
```bash
# Test API key
python test_api_quick.py

# Check key in config
grep youtube_api_key config/config_comprehensive.yaml
```

#### Quota Tracking Issues
```bash
# Verify database schema and today's quota spend
python daily.py status
```

#### Resume Issues
```bash
# Check checkpoint
cat data/checkpoints/latest_checkpoint.json | python -m json.tool

# Verify checkpoint quota
python -c "
import json
with open('data/checkpoints/latest_checkpoint.json') as f:
    print('Cumulative:', json.load(f)['quota_cumulative'])"
```

## 📈 Performance Expectations

### Collection Rates (Approximate)
- **Channels**: 50-100 per hour
- **Videos**: 1,000-5,000 per hour
- **Comments**: 10,000-50,000 per hour

### Quota Usage (Per Channel Average)
- Small channel (<100 videos): ~50-100 units
- Medium channel (100-1000 videos): ~200-500 units
- Large channel (1000+ videos): ~500-2000 units

### Time Estimates
- **Per channel**: 30 seconds to 5 minutes
- **Full collection** (2,700 channels): 24-48 hours
- **With quota limits**: May span 2-3 days

## ✅ Post-Collection Verification

### 11. Final Checks
- [ ] Collection completed or interrupted cleanly
- [ ] Final statistics logged
- [ ] Database integrity verified
- [ ] Quota usage within limits
- [ ] Checkpoint saved for potential resume

### 12. Data Validation
```bash
# View final statistics
python view_data.py --stats

# Check collection coverage
sqlite3 data/youtube_monitoring.db "
SELECT
    COUNT(DISTINCT channel_id) as channels,
    COUNT(DISTINCT video_id) as videos,
    COUNT(DISTINCT comment_id) as comments
FROM channels
JOIN videos USING(channel_id)
LEFT JOIN comments USING(video_id);"

# Verify quota accuracy (actual charges, per endpoint)
sqlite3 data/youtube_monitoring.db \
  "SELECT day, endpoint, calls, units FROM quota_ledger ORDER BY day DESC, units DESC;"
```

## 📝 Documentation

### Record These Values
- Start time: _________________
- End time: _________________
- Channels processed: _________________
- Videos collected: _________________
- Comments collected: _________________
- Total quota used: _________________
- Final cumulative quota: _________________
- Any errors encountered: _________________

## 🔄 Next Steps

1. **If collection incomplete**: Use `--resume` flag next day
2. **If quota exhausted**: Wait for daily reset (midnight PT)
3. **For analysis**: Export data using `view_data.py`
4. **For backup**: Copy `data/youtube_monitoring.db`

## 📞 Support

If issues arise:
1. Check `logs/pipeline.log` for detailed errors
2. Run `python verify_production.py` for system check
3. Consult `CLAUDE.md` for detailed documentation
4. Use SQL queries in `verify_queries.sql` for debugging