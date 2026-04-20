# Data Entry Procedure: Fixing Problematic YouTube URLs

## Overview

**File to edit**: `data/problematic_urls_to_fix.csv`
**Total entries to fix**: 103
**After fixing**: Update `data/sources.csv` with corrected URLs

---

## Issue Types Summary

| Issue Type | Count | Action Required |
|------------|-------|-----------------|
| BARE_NAME | 82 | Convert to proper format (usually works, but verify) |
| VIDEO_URL | 11 | Find the channel that uploaded the video |
| PLAYLIST_URL | 6 | Find the channel that owns the playlist |
| NON_YOUTUBE | 4 | Find if outlet has a YouTube channel, or mark as NONE |

---

## Step-by-Step Procedure

### For Each Entry:

1. Open `data/problematic_urls_to_fix.csv` in a spreadsheet editor
2. For each row, follow the procedure for its `issue_type`
3. Fill in the `corrected_url` column with the proper format
4. After all corrections, run the update script (provided below)

---

## Procedure by Issue Type

### 1. BARE_NAME (82 entries)

**Current format**: `https://www.youtube.com/channelname`
**Target format**: `https://www.youtube.com/@channelname` or `https://www.youtube.com/channel/UC...`

**Steps**:
1. Open the current URL in browser
2. If it redirects to a channel page:
   - Copy the URL from the address bar
   - It should now be in format `/@handle` or `/channel/UC...`
3. If it shows "This page isn't available":
   - Try adding `@` prefix: `youtube.com/@channelname`
   - If still not found, search YouTube for the brand name
   - If no channel exists, enter `NONE` in corrected_url

**Example**:
```
Current:   https://www.youtube.com/trtdeutsch
Browser:   Opens and redirects to https://www.youtube.com/@taborttrt (example)
Corrected: https://www.youtube.com/@taborttrt
```

**Quick check**: Most BARE_NAME entries will work if you just visit them - YouTube redirects automatically. Copy the final URL after redirect.

---

### 2. VIDEO_URL (11 entries)

**Current format**: `https://www.youtube.com/watch?v=VIDEO_ID`
**Target format**: Channel URL of the video uploader

**Steps**:
1. Open the video URL in browser
2. Click on the channel name (below the video title)
3. Copy the channel URL from address bar
4. If video is unavailable/deleted:
   - Search YouTube for the brand name
   - If no channel found, enter `NONE`

**Example**:
```
Current:   https://www.youtube.com/watch?v=p8XlG8aen_4
Action:    Click on channel name under video
Corrected: https://www.youtube.com/@ChannelHandle
```

---

### 3. PLAYLIST_URL (6 entries)

**Current format**: `https://www.youtube.com/playlist?list=PLAYLIST_ID`
**Target format**: Channel URL of the playlist owner

**Steps**:
1. Open the playlist URL in browser
2. Look for the channel name/avatar at the top of the playlist
3. Click on it to go to the channel page
4. Copy the channel URL
5. If playlist is unavailable:
   - Search YouTube for the brand name
   - If no channel found, enter `NONE`

**Example**:
```
Current:   https://www.youtube.com/playlist?list=PLRQmtEOmt7KKZkwCzXpLmXCqNZUMVM0Ez
Action:    Click channel name on playlist page
Corrected: https://www.youtube.com/channel/UCxxxxxxxxxx
```

---

### 4. NON_YOUTUBE (4 entries)

**Current format**: LinkedIn URL, other video platforms, etc.
**Target format**: Find YouTube channel or mark as NONE

**Steps**:
1. Note the domain and brand name
2. Go to YouTube and search for the brand name
3. Find the official channel (verify by checking About page, website links)
4. Copy the channel URL
5. If no YouTube channel exists, enter `NONE`

**The 4 NON_YOUTUBE entries**:
| Domain | Brand | Current URL | Action |
|--------|-------|-------------|--------|
| andreaskalcker.com | AndreasKalcker | dioxitube.com | Search YouTube for "Andreas Kalcker" |
| dailyliberal.com.au | The Daily Liberal | LinkedIn URL | Search YouTube for "Daily Liberal Australia" |
| cjr.org | Columbia Journalism Review | x.com/CJR | Search YouTube for "Columbia Journalism Review" |
| andreaskalcker.com | AndreasKalcker | dioxitube.com | (duplicate) |

---

## Accepted URL Formats

When entering corrected URLs, use one of these formats:

| Format | Example | Notes |
|--------|---------|-------|
| Channel ID | `https://www.youtube.com/channel/UCxxxxxxxxxxxxxxxxxxxxxxxx` | Best - direct ID |
| Handle | `https://www.youtube.com/@channelhandle` | Good - modern format |
| Custom URL | `https://www.youtube.com/c/customname` | OK - will be resolved |
| Legacy user | `https://www.youtube.com/user/username` | OK - will be resolved |
| No channel | `NONE` | Use when channel doesn't exist |

---

## Special Cases

### Duplicate Entries
Some entries appear multiple times (same channel for different domains):
- Row 352 & 2246: trtdeutsch.com (same channel)
- Row 528 & 2681: qactus.fr (same video URL)
- Row 1808-1824: Multiple CityNews domains sharing same channel

**Action**: Fix one, copy the corrected URL to all duplicates.

### Search Results URL
Some entries point to YouTube search results (e.g., The Times):
```
Current: https://www.youtube.com/results?search_query=the+times+and+the+sunday+times
```
**Action**: Perform the search manually, identify the official channel, copy its URL.

---

## Validation Checklist

Before saving, verify each corrected URL:
- [ ] Starts with `https://www.youtube.com/` (or `https://youtube.com/`)
- [ ] Contains `/channel/`, `/@`, `/c/`, or `/user/`
- [ ] OR is marked as `NONE`
- [ ] No trailing slashes or extra parameters

---

## After Completing All Corrections

### Option A: Manual Update
1. Open `data/sources.csv`
2. For each row in `problematic_urls_to_fix.csv`:
   - Find the matching row by `row_number`
   - Update the `Youtube` column with `corrected_url`
   - If `NONE`, clear the Youtube cell (leave empty)

### Option B: Automated Update (recommended)
Save your completed `problematic_urls_to_fix.csv` and run:
```bash
python scripts/apply_url_corrections.py
```
(Script will be created after you complete the corrections)

---

## Progress Tracking

Use this checklist to track your progress:

- [ ] BARE_NAME entries (82 total)
  - [ ] Rows 352-3157 (first batch)
  - [ ] Rows 4157-6688 (second batch)
  - [ ] Rows 7005-12799 (third batch)
- [ ] VIDEO_URL entries (11 total)
- [ ] PLAYLIST_URL entries (6 total)
- [ ] NON_YOUTUBE entries (4 total)

---

## Tips for Speed

1. **Batch similar entries**: Open all BARE_NAME URLs in browser tabs, then copy corrected URLs
2. **Use browser history**: If you've visited a channel before, it may autocomplete
3. **Check duplicates first**: Fix one instance, then copy to duplicates
4. **Note patterns**: CityNews entries all share the same channel - fix once, apply to all 6

---

## Questions?

If you encounter an entry that doesn't fit any category:
- Note the row number and issue
- We can review it together before finalizing
