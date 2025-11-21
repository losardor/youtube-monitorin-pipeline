# Transcript Collection Feasibility Guide

## Quick Answer

**YES, it's feasible** using `youtube-transcript-api` (unofficial but practical)

**Expected Results:**
- Success rate: 40-60% of videos have transcripts
- Time: 2-8 days (running continuously)
- Cost: $0 (no quota, no authentication)
- Storage: ~10-50 GB for text transcripts

---

## Why Official API Doesn't Work

### YouTube Data API v3 Limitations

The official `captions.download` endpoint:
- ❌ Requires OAuth 2.0 (not just API key)
- ❌ Only works for videos YOU own
- ❌ Cannot access other channels' captions
- ❌ Designed for content creators, not researchers

**Conclusion:** Official API is not viable for your research use case.

---

## Recommended Solution: youtube-transcript-api

### What It Is
- **Unofficial library** that extracts transcripts via web scraping
- **Widely used** in research (100K+ downloads/month)
- **No authentication** required
- **No quota limits**
- **Works for any public video** with captions

### Installation
```bash
pip install youtube-transcript-api
```

### Legal/Ethical Considerations

**Against YouTube ToS?**
- ⚠️ Technically yes (automated scraping)
- ✅ BUT: Only accesses publicly available data
- ✅ Widely used in published research
- ✅ No commercial use in your case
- ✅ Similar to other web scraping for research

**Academic Precedent:**
- Many published papers use this approach
- Generally accepted for research purposes
- Disclose methodology in paper
- Consider it "gray area" research tooling

---

## Feasibility Analysis for Your Dataset

### Your Dataset Size
- **Videos collected:** 150,000 - 350,000
- **Expected with transcripts:** 60,000 - 210,000 (40-60%)
- **Languages:** Primarily IT, DE, FR, EN

### Time Estimates

**Per video processing:**
- API call: ~1 second
- Delay (respectful): ~0.5 seconds
- Total: ~1.5 seconds per video

**Total time:**
```
Pessimistic (350K videos): 350,000 × 1.5s = 145 hours = 6 days
Optimistic (150K videos):  150,000 × 1.5s = 62 hours = 2.6 days
Realistic (200K videos):   200,000 × 1.5s = 83 hours = 3.5 days
```

**Timeline:** 3-6 days running 24/7 on server

### Storage Requirements

**Per transcript:**
- Average news video: 5-15 minutes
- Average transcript: 1,000-3,000 words
- Text file size: 10-30 KB
- JSON with timestamps: 50-150 KB

**Total storage:**
```
100,000 transcripts × 100 KB average = 10 GB
200,000 transcripts × 100 KB average = 20 GB
```

**Database storage:**
- Text + JSON in SQLite: 15-40 GB
- Separate JSON files: 10-30 GB

**Total needed:** ~50 GB (safe estimate)

---

## Success Rate Expectations

### Transcript Availability

**Videos with transcripts (~40-60%):**
- Manual captions: 10-20%
- Auto-generated: 30-50%
- No transcripts: 40-60%

**Why some videos lack transcripts:**
- Older videos (pre-auto-captions era)
- Non-speech content (music, b-roll)
- Creator disabled captions
- Language not supported by auto-captions
- Short videos (<1 minute)

### Language Distribution (Expected)

Based on European news outlets:
```
Italian (IT):  30-40%
German (DE):   25-35%
French (FR):   15-25%
English (EN):  10-20%
Spanish (ES):   5-10%
Other:          5-10%
```

---

## Implementation Steps

### Step 1: Install Library (On Server)

```bash
ssh user@YOUR_SERVER
cd youtube_monitoring_pipeline
source venv/bin/activate
pip install youtube-transcript-api
```

### Step 2: Run Transcript Downloader

```bash
# Test with small sample first
python download_transcripts.py

# It will:
# - Load all videos from database
# - Try to get transcripts for each
# - Save to database + JSON files
# - Resume-capable (skips already downloaded)
```

### Step 3: Monitor Progress

```bash
# Check progress
tail -f logs/transcript_download.log

# Or check database
sqlite3 data/youtube_monitoring.db "SELECT COUNT(*) FROM transcripts"

# Estimate completion
# Videos: 200,000
# Downloaded: 50,000
# Progress: 25%
# Remaining: ~60 hours
```

### Step 4: Handle Interruptions

The script is **resume-capable:**
- Skips already-downloaded transcripts
- Can stop and restart anytime
- No data loss on interruption

---

## Alternative: Batch Processing Strategy

If 3-6 days is too long, use multiple parallel processes:

### Option A: Split by Channel

```bash
# Terminal 1: Channels 1-1000
python download_transcripts.py --start 0 --end 1000

# Terminal 2: Channels 1001-2000
python download_transcripts.py --start 1001 --end 2000

# Terminal 3: Channels 2001-3000
python download_transcripts.py --start 2001 --end 3000
```

**Time reduction:** 3-4x faster (3-6 days → 1-2 days)

### Option B: Multiple Servers

Run on 3-5 cheap servers simultaneously:
- Split video list into chunks
- Each server processes its chunk
- Merge databases afterward

**Time reduction:** 3-5x faster (3-6 days → <1 day)

---

## Data Quality Considerations

### What You Get

**Auto-generated transcripts:**
- ✅ Free and available for most videos
- ⚠️ ~10-20% word error rate
- ⚠️ No punctuation (usually)
- ⚠️ Poor with accents/dialects
- ⚠️ Bad with technical terms

**Manual transcripts:**
- ✅ High quality
- ✅ Proper punctuation
- ✅ Better accuracy
- ❌ Only ~10-20% of videos

### Research Implications

**Suitable for:**
- ✅ Topic modeling
- ✅ Keyword analysis
- ✅ Content classification
- ✅ Sentiment analysis (with caution)
- ✅ Temporal trends

**Problematic for:**
- ⚠️ Fine-grained linguistic analysis
- ⚠️ Quote extraction
- ⚠️ Proper name identification
- ⚠️ Discourse analysis

**Recommendation:** 
- Use transcripts for high-level content analysis
- Note auto-generated limitations in methodology
- Consider manual validation of samples

---

## Cost-Benefit Analysis

### Pros
✅ **Free** (no API quota)
✅ **Fast** (3-6 days total)
✅ **Reliable** (proven library)
✅ **Resume-capable** (can stop/start)
✅ **Large coverage** (40-60% of videos)
✅ **Multilingual** (supports your languages)

### Cons
⚠️ **Unofficial** (against ToS)
⚠️ **Auto-caption quality** (10-20% error rate)
⚠️ **Not all videos** (40-60% missing)
⚠️ **Could break** (if YouTube changes)
⚠️ **Storage needed** (~50 GB)

### Verdict
**Highly Recommended** for research purposes

The benefits far outweigh the drawbacks for your use case.

---

## Comparison with Alternatives

| Method | Cost | Time | Coverage | Quality | Legal |
|--------|------|------|----------|---------|-------|
| **youtube-transcript-api** | $0 | 3-6 days | 40-60% | Medium | Gray area |
| YouTube API (official) | N/A | N/A | 0% | N/A | Doesn't work |
| Whisper (generate own) | $10K+ | 6+ months | 100% | High | Legal |
| Commercial services | $5K-20K | 1-4 weeks | 40-60% | Medium | Legal |

**Clear winner:** youtube-transcript-api for research

---

## Methodology Section Language

### How to Report in Paper

**Full disclosure approach:**
```
"We obtained video transcripts using the youtube-transcript-api library 
(unofficial but widely used in research), which extracts publicly available 
auto-generated and manual captions via web scraping. Transcripts were 
available for 45% of collected videos (n=90,000). We acknowledge that 
auto-generated transcripts have estimated word error rates of 10-20% and 
use them primarily for topic-level content analysis rather than fine-grained 
linguistic analysis."
```

**Brief approach:**
```
"Video transcripts were obtained when available (45% of videos, n=90,000) 
using publicly accessible caption data. We note that auto-generated captions 
have approximate 10-20% error rates."
```

---

## Recommendations

### For Your Project

1. ✅ **DO IT** - The benefits are substantial
2. ✅ **Start now** - Run in parallel with existing collection
3. ✅ **Run on server** - Let it run for 3-6 days
4. ✅ **Disclose methodology** - Be transparent in paper
5. ✅ **Validate sample** - Check quality on 100-200 videos

### Timeline Suggestion

**Week 1 (Current):**
- Finish video/comment collection (1-2 days)
- Start transcript download (day 3)

**Week 2:**
- Transcript download completes (days 4-9)
- Export all data
- Begin analysis

### Storage Planning

**Current database:** ~50-80 GB (videos + comments)
**Add transcripts:** +15-40 GB
**Total:** ~65-120 GB

Make sure your server has **150 GB free** to be safe.

---

## Next Steps

### Ready to Start?

**1. Install the library:**
```bash
ssh user@YOUR_SERVER
cd youtube_monitoring_pipeline
source venv/bin/activate
pip install youtube-transcript-api
```

**2. Upload the script:**
```bash
# From local machine
scp download_transcripts.py user@SERVER:~/youtube_monitoring_pipeline/
```

**3. Test with small batch:**
```bash
# On server
python3 << 'EOF'
from youtube_transcript_api import YouTubeTranscriptApi

# Test with a known video
try:
    transcript = YouTubeTranscriptApi.get_transcript('dQw4w9WgXcQ')
    print(f"✓ Library works! Got {len(transcript)} segments")
except Exception as e:
    print(f"✗ Error: {e}")
EOF
```

**4. Run full collection:**
```bash
# Start in screen session
screen -S transcripts
python download_transcripts.py
# Ctrl+A, D to detach
```

**5. Monitor:**
```bash
# Check progress
sqlite3 data/youtube_monitoring.db "SELECT COUNT(*) FROM transcripts"

# Estimate completion time
# If 10,000 done in 4 hours, and need 200,000 total:
# Remaining: 190,000 × (4h / 10,000) = 76 hours = 3.2 days
```

---

## Questions?

### Common Issues

**Q: "TranscriptsDisabled" error?**
A: Video owner disabled captions. ~10-20% of videos. Normal.

**Q: "NoTranscriptFound" error?**
A: No captions available (auto or manual). ~40-60% of videos. Normal.

**Q: Script crashes?**
A: Resume-capable! Just restart it, skips already-downloaded.

**Q: Taking too long?**
A: Run multiple parallel processes (split by channel ID).

**Q: Storage running out?**
A: Stop script, export transcripts to external storage, clear space, resume.

---

## Summary

**Feasibility:** ✅ Highly feasible  
**Cost:** $0  
**Time:** 3-6 days  
**Coverage:** 40-60% of videos  
**Quality:** Medium (auto-captions have errors)  
**Legal:** Gray area but research-acceptable  
**Recommendation:** **DO IT** - substantial research value  

The transcripts will greatly enhance your analysis capabilities!
