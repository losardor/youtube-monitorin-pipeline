# Complete Migration & Comprehensive Collection Plan

## 🎯 Summary

You're ready to migrate from **Overview Strategy** (quick sampling) to **Comprehensive Strategy** (complete data collection) on a remote server.

---

## 📊 What You've Accomplished So Far

✅ Successfully collected 31 channels with overview mode  
✅ Gathered 1,395 videos and 535 comments  
✅ Used only 1,125 quota units (very efficient!)  
✅ Proven the pipeline works reliably  
✅ API key is validated and working  

---

## 🚀 New Files Created for You

### 1. **collect_comprehensive.py**
- Comprehensive data collector
- Collects ALL videos and ALL comments (no limits)
- Built-in checkpointing and resume capability
- Progress tracking and error handling

### 2. **config/config_comprehensive.yaml**
- Configuration for unlimited collection
- Higher quotas (1M units/day)
- Checkpoint settings
- Comprehensive delays for API respect

### 3. **SERVER_MIGRATION_GUIDE.md**
- Complete server setup instructions
- Package and upload instructions
- Screen/tmux usage for long-running processes
- Monitoring and management scripts

### 4. **STRATEGY_COMPARISON.md**
- Detailed comparison of overview vs comprehensive
- Quota usage breakdowns
- When to use each strategy

### 5. **test_comprehensive.py**
- Local test script before server deployment
- Validates configuration
- Estimates quota usage

---

## 📋 Step-by-Step Checklist

### Phase 1: Local Testing (Today - 1 hour)

```bash
# 1. Copy your API key to the new config
cd /Users/losardo/Documents/Youtube/youtube_monitoring_pipeline
cp config/config.yaml config/config_comprehensive.yaml

# Edit to ensure API key is there (should already be)
nano config/config_comprehensive.yaml

# 2. Run validation
python test_comprehensive.py

# 3. Test with 3 channels (will take ~15 minutes)
python collect_comprehensive.py --sources data/sources.csv --max-channels 3

# 4. Compare results
python view_data.py --stats
# You should see MANY more comments per channel than before!
```

**Expected Results:**
- Before (overview): ~100 comments from 3 channels
- After (comprehensive): ~5,000-15,000 comments from same 3 channels

---

### Phase 2: Request Quota Increase (Today - 5 minutes)

```bash
# While local test runs, request quota increase:

1. Go to: https://console.cloud.google.com/apis/api/youtube.googleapis.com/quotas
2. Select your project
3. Find "Queries per day"
4. Click checkbox → "EDIT QUOTAS"
5. Request: 1,000,000 units/day
6. Justification:
   "Academic research project analyzing YouTube content from 12,000+ news 
   outlets for computational social science study on polarization, toxicity, 
   and trust in online media. Need to collect comprehensive video and comment 
   data for longitudinal analysis."

Response time: 1-3 business days
```

---

### Phase 3: Server Setup (Day 2 - 1 hour)

**Choose a server:**
- **Recommended**: Hetzner CPX31 (€9/month, 4GB RAM)
- **Alternative**: DigitalOcean Droplet ($24/month, 4GB RAM)
- **Alternative**: AWS t3.medium ($30-40/month)

**Follow SERVER_MIGRATION_GUIDE.md:**

```bash
# Quick version:
# 1. Package project locally
cd /Users/losardo/Documents/Youtube/youtube_monitoring_pipeline
tar -czf youtube_pipeline.tar.gz \
    --exclude='venv' --exclude='*.db' --exclude='__pycache__' \
    src/ config/ data/sources.csv *.py requirements.txt

# 2. Upload to server
scp youtube_pipeline.tar.gz user@YOUR_SERVER_IP:~/

# 3. SSH to server and setup
ssh user@YOUR_SERVER_IP
tar -xzf youtube_pipeline.tar.gz
cd youtube_monitoring_pipeline
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 4. Test on server
python collect_comprehensive.py --sources data/sources.csv --max-channels 3
```

---

### Phase 4: Wait for Quota Approval (Days 2-4)

While waiting:

```bash
# Run daily overview collections with existing 10K quota
python collect.py --sources data/sources.csv --max-channels 600

# Each day you can process ~600 more channels with overview mode
# This gives you a baseline dataset while waiting for comprehensive quota
```

---

### Phase 5: Start Comprehensive Collection (Day 5 - 2 days runtime)

**Once quota is approved:**

```bash
# SSH to server
ssh user@YOUR_SERVER_IP
cd youtube_monitoring_pipeline
source venv/bin/activate

# Start in screen session (survives disconnect)
screen -S youtube_collection

# Update config with new quota
nano config/config_comprehensive.yaml
# Change: daily_quota: 1000000

# Start comprehensive collection of ALL 12,847 channels
python collect_comprehensive.py --sources data/sources.csv

# Detach from screen: Ctrl+A then D
# Collection will continue in background
```

**Monitor progress:**
```bash
# Check anytime with:
screen -r youtube_collection  # See live output
# Detach: Ctrl+A then D

# Or check stats:
python view_data.py --stats
```

**Expected timeline:**
- Day 1: ~6,500 channels, ~500K videos, ~3M comments
- Day 2: ~6,347 channels, ~500K videos, ~3M comments
- **Total**: ~1M videos, ~6M comments, 50-80GB database

---

### Phase 6: Download and Analyze (Day 7)

```bash
# Export data on server
./export_data.sh

# Download to local machine
scp user@SERVER:~/youtube_monitoring_pipeline/exports_*.tar.gz .
scp user@SERVER:~/youtube_monitoring_pipeline/data/youtube_monitoring.db .

# Extract and analyze
tar -xzf exports_*.tar.gz
python view_data.py --stats
```

---

## 💰 Cost Estimate

### Server Costs (2 days collection + 1 day analysis)
- Hetzner CPX31: €9/month (cancel after) = **€0.90**
- DigitalOcean: $24/month (cancel after) = **$2.40**
- AWS t3.medium: ~$40/month = **$4.00**

### Data Storage
- If keeping server: €9-40/month
- If downloading: Free (local storage)

**Recommendation**: Use cheap server for collection, download results, delete server.  
**Total cost: ~$3-5 one-time**

---

## 🎓 Research Dataset You'll Have

After comprehensive collection:

**Channels**: 5,000-7,000 (42-60% success rate)  
**Videos**: ~500,000-700,000  
**Comments**: ~5-10 million  
**Views**: ~5-10 billion total  
**Database**: 50-80 GB  
**Time period**: All historical data up to collection date  

**Metadata includes:**
- Channel info (subscribers, total views)
- Video metadata (title, description, tags, topics)
- Full comment text with threading
- Engagement metrics (views, likes, comments)
- Publication timestamps
- Source ratings and orientations from your CSV

---

## 🔬 Analysis Possibilities

With comprehensive dataset:

1. **Polarization Analysis**
   - Comment toxicity by source orientation
   - Echo chamber formation in comment threads
   - Cross-channel commenter patterns

2. **Temporal Trends**
   - Engagement evolution over time
   - Topic shifts across political spectrum
   - Comment sentiment changes

3. **Network Analysis**
   - Commenter networks across channels
   - Channel collaboration patterns
   - Information spread dynamics

4. **Content Analysis**
   - NLP on video titles/descriptions
   - Comment language patterns
   - Narrative framing differences

---

## ⚡ Quick Start Commands

**Test locally right now:**
```bash
python test_comprehensive.py
```

**Test comprehensive with 3 channels:**
```bash
python collect_comprehensive.py --sources data/sources.csv --max-channels 3
```

**Compare overview vs comprehensive:**
```bash
python view_data.py --stats
python view_data.py --videos 20
python view_data.py --comments 20
```

**Package for server:**
```bash
tar -czf youtube_pipeline.tar.gz \
    --exclude='venv' --exclude='*.db' --exclude='__pycache__' \
    src/ config/ data/sources.csv *.py requirements.txt
```

---

## 📞 Next Steps - What Would You Like to Do?

**Option A**: Test comprehensive mode locally first
```bash
python test_comprehensive.py
```

**Option B**: Start server setup now
- Follow SERVER_MIGRATION_GUIDE.md
- I can help with any step

**Option C**: Continue with overview mode while waiting for quota
```bash
python collect.py --sources data/sources.csv --max-channels 500
```

**Option D**: Review the comparison document
```bash
cat STRATEGY_COMPARISON.md
```

---

## 🎯 Recommended: Quick Test Now

**Run this right now to see the difference:**

```bash
# Test comprehensive mode with just 2 channels
python collect_comprehensive.py --sources data/sources.csv --max-channels 2

# This will take ~10-20 minutes
# You'll see MUCH more data collected per channel

# Then compare:
python view_data.py --stats
```

This shows you exactly what comprehensive mode will do before migrating to server!

---

## Questions?

I'm here to help with:
- ✅ Server selection and setup
- ✅ Any configuration questions
- ✅ Testing and validation
- ✅ Data export and analysis
- ✅ Troubleshooting any issues

**What would you like to do next?** 🚀
