# Collection Strategy Comparison

## Overview Strategy (Current) vs Comprehensive Strategy (New)

---

## Overview Strategy - Quick & Conservative

**Purpose:** Get a representative sample quickly with minimal quota usage

**Settings:**
- ✓ Max 50 videos per channel
- ✓ Max 100 comments per video
- ✓ Comments only from first 5 videos
- ✓ ~15 units per channel

**Best for:**
- Testing and development
- Daily monitoring/updates
- Limited quota situations
- Quick overviews

**Results from your test:**
- 31 channels in ~1,100 quota units
- ~45 videos per channel (good sample)
- 535 comments total (limited by 5-video restriction)

---

## Comprehensive Strategy - Complete & Thorough

**Purpose:** Collect ALL available data for complete analysis

**Settings:**
- ✓ ALL videos from channel (no limit)
- ✓ ALL comments from ALL videos (no limit)
- ✓ Pagination through all pages
- ✓ ~140 units per channel (average)

**Best for:**
- Complete dataset collection
- Longitudinal analysis
- Maximum data for research
- One-time comprehensive scraping

**Projected for 12,847 channels:**
- ~1,800,000 quota units needed
- ~2 days with 1M quota/day
- ~500,000-700,000 videos
- ~5-10 million comments
- ~50-100 GB database size

---

## Side-by-Side Comparison

| Feature | Overview | Comprehensive |
|---------|----------|---------------|
| **Videos per channel** | 50 max | Unlimited |
| **Comments per video** | 100 max, 5 videos only | Unlimited, all videos |
| **Comment pagination** | Single page | All pages |
| **Caption metadata** | No | Yes |
| **Quota per channel** | ~15 units | ~140 units |
| **Speed** | Fast | Slower |
| **Checkpointing** | No | Yes |
| **Resume capability** | No | Yes |
| **Data completeness** | Sample | Complete |

---

## When to Use Each

### Use Overview Strategy When:
- ✓ Testing the pipeline
- ✓ Daily updates on channels you already collected
- ✓ Monitoring new content
- ✓ You have limited quota
- ✓ You want quick results

### Use Comprehensive Strategy When:
- ✓ Building a complete research dataset
- ✓ You have 1M+ quota/day
- ✓ Running on a remote server
- ✓ You need ALL historical data
- ✓ Doing deep analysis on comment patterns
- ✓ Time is not critical

---

## Example Outputs

### Overview Strategy - 1 Channel
```
Channel: BBC News
Videos collected: 50 (most recent)
Comments collected: 500 (from 5 videos)
Quota used: 15 units
Time: 2 minutes
```

### Comprehensive Strategy - 1 Channel  
```
Channel: BBC News
Videos collected: 8,432 (ALL videos)
Comments collected: 245,678 (from ALL videos)
Quota used: 142 units
Time: 45 minutes
```

---

## Quota Usage Breakdown

### Overview (per channel):
```
Channel info:        1 unit
Video list (1 page): 1 unit
Video details:       1 unit (50 videos)
Comments (5 videos): 5 units
Caption list:        0 units (disabled)
-------------------
Total: ~15 units
```

### Comprehensive (per channel with 8,000 videos):
```
Channel info:        1 unit
Video list (160 pg): 160 units
Video details:       160 units (8k videos in batches)
Comments (all):      ~200 units (varies by comment count)
Caption list:        ~400 units (50 per video, sampled)
-------------------
Total: ~140 units (average)
Can be 50-500 depending on channel size
```

---

## Recommendations for Your 12,847 Channels

### Phase 1: Validation (Local, Overview Strategy)
```bash
python collect.py --sources data/sources.csv --max-channels 100
```
- Validates all channel URLs work
- Identifies failed/deleted channels
- Creates baseline dataset
- Uses ~1,500 quota units

### Phase 2: Comprehensive Collection (Server)
```bash
python collect_comprehensive.py --sources data/sources.csv
```
- Collects ALL data from ALL channels
- Runs for ~2 days
- Uses ~1.8M quota units
- Checkpoints every 10 channels
- Can resume if interrupted

### Phase 3: Updates (Monthly, Overview Strategy)
```bash
python collect.py --sources data/sources.csv --start-date "2025-12-01"
```
- Collect only new content since last run
- Quick monthly updates
- Minimal quota usage

---

## Data Size Estimates

### Overview Strategy (12,847 channels):
- Database: ~5 GB
- Videos: ~600,000
- Comments: ~300,000
- Export CSVs: ~2 GB

### Comprehensive Strategy (12,847 channels):
- Database: ~50-80 GB
- Videos: ~500,000-700,000
- Comments: ~5-10 million
- Export CSVs: ~15-25 GB

---

## Migration Checklist

Before migrating to comprehensive strategy:

- [ ] Test comprehensive mode locally with 5 channels
- [ ] Verify quota increase approved (1M units/day)
- [ ] Setup remote server (4GB RAM minimum)
- [ ] Upload project to server
- [ ] Test with 10 channels on server
- [ ] Start full collection with screen/tmux
- [ ] Setup monitoring cron job
- [ ] Plan data download strategy

---

## Testing Comprehensive Mode Locally

Test before deploying to server:

```bash
# Test with 3 channels in comprehensive mode
python collect_comprehensive.py \
    --sources data/sources.csv \
    --max-channels 3 \
    --config config/config_comprehensive.yaml

# Check results
python view_data.py --stats

# Compare with overview mode results
# You should see MANY more videos and comments per channel
```

Expected differences:
- Overview: ~45 videos, ~100 comments per channel
- Comprehensive: 100-5000 videos, 500-50000 comments per channel

---

## Questions?

**Q: Can I run both strategies?**
A: Yes! Use overview for quick checks, comprehensive for full collection.

**Q: Will comprehensive overwrite my overview data?**
A: No, it uses the same database and will add to it.

**Q: How do I switch back to overview?**
A: Just use `collect.py` instead of `collect_comprehensive.py`

**Q: Can I pause and resume comprehensive collection?**
A: Yes! Press Ctrl+C and restart with `--resume` flag
