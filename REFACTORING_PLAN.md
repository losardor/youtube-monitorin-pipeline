# Code Deduplication and Refactoring Plan

## Current Problem

The codebase has **4 different entry points** for data collection, causing confusion and inconsistency:

| Script | Size | Purpose | Issues |
|--------|------|---------|--------|
| `src/collector.py` | Stub | Original design (class-based) | Incomplete, not functional |
| `run_collector.py` | 1KB | Wrapper for src/collector.py | References non-functional code |
| `collect.py` | 7KB | Standalone simple collector | Limited features, outdated |
| `collect_comprehensive.py` | 17KB | First comprehensive version | Has bugs, replaced by fixed version |
| `collect_comprehensive_fixed.py` | 24KB | **Current production script** | Working, but name is confusing |

**Additional Issues:**
- Shell scripts reference wrong file (`collect_comprehensive.py` instead of `collect_comprehensive_fixed.py`)
- README documents `src/collector.py` which doesn't work
- CLAUDE.md documents multiple conflicting entry points
- Inconsistent naming conventions

## Recommended Strategy

### Phase 1: Standardize on Single Entry Point

**Decision:** Use `collect.py` as the canonical entry point name (standard Python convention)

**Actions:**
1. Rename `collect_comprehensive_fixed.py` → `collect.py` (overwrite old version)
2. Move it to root directory (already there)
3. Update all documentation
4. Update all shell scripts
5. Update terminal aliases

**Rationale:**
- `collect.py` is the most intuitive name
- Root-level placement is standard for main scripts
- Single command: `python collect.py --sources data/sources.csv`

### Phase 2: Clean Up Deprecated Files

**Files to Remove:**
```
❌ collect_comprehensive.py        # Buggy version
❌ collect_comprehensive_fixed.py  # Will be renamed to collect.py
❌ run_collector.py                # Unnecessary wrapper
❌ src/collector.py                # Non-functional stub
```

**Files to Keep:**
```
✅ collect.py                      # Main entry point (from collect_comprehensive_fixed.py)
✅ src/youtube_client.py           # API wrapper
✅ src/database.py                 # Database layer
✅ src/utils/helpers.py            # Utilities
```

### Phase 3: Update Documentation and Scripts

**Update these files:**
1. `README.md` - Change all references to `python collect.py`
2. `CLAUDE.md` - Update main script reference
3. `DEPLOYMENT.md` - Update deployment commands
4. `auto_resume.sh` - Change script name and process check
5. `status.sh` - Update process name and resume command
6. Terminal aliases in `~/.zshrc` - Update command shortcuts

### Phase 4: Verify Configuration

**Ensure config files align:**
- `config/config.yaml.template` - For development/testing
- `config/config_comprehensive.yaml.template` - For production

**Make sure `collect.py` can use both:**
```python
parser.add_argument('--config', default='config/config.yaml')
```

## Implementation Steps

### Step 1: Backup Current State
```bash
git checkout -b refactor-collectors
git add .
git commit -m "Backup before refactoring collectors"
```

### Step 2: Rename Main Script
```bash
# Overwrite old collect.py with the working version
cp collect_comprehensive_fixed.py collect.py

# Verify it works
python collect.py --sources data/sources.csv --max-channels 1 --config config/config.yaml
```

### Step 3: Remove Deprecated Files
```bash
git rm collect_comprehensive.py
git rm collect_comprehensive_fixed.py
git rm run_collector.py
git rm src/collector.py
```

### Step 4: Update Shell Scripts

**`auto_resume.sh`:**
```bash
# Change line 15:
if pgrep -f "collect_comprehensive.py" > /dev/null; then
# To:
if pgrep -f "collect.py" > /dev/null; then

# Change line 28:
python collect_comprehensive.py --sources data/sources.csv --resume >> $LOG_FILE 2>&1
# To:
python collect.py --sources data/sources.csv --resume >> $LOG_FILE 2>&1
```

**`status.sh`:**
```bash
# Change line 14:
if pgrep -f "collect_comprehensive.py" > /dev/null; then
# To:
if pgrep -f "collect.py" > /dev/null; then

# Change line 16:
PID=$(pgrep -f "collect_comprehensive.py")
# To:
PID=$(pgrep -f "collect.py")

# Change line 36:
echo "  Resume with: python collect_comprehensive.py --resume"
# To:
echo "  Resume with: python collect.py --resume"
```

### Step 5: Update Documentation

**`README.md`:**
```markdown
# Change all occurrences:
python src/collector.py --sources path/to/sources.csv
# To:
python collect.py --sources path/to/sources.csv
```

**`CLAUDE.md`:**
```markdown
# Update main script references
**`collect.py`** - Production collector with comprehensive strategy:
```

**`DEPLOYMENT.md`:**
```markdown
# Update all command examples
python collect.py --sources data/sources.csv --resume
```

### Step 6: Update Terminal Aliases

**In `~/.zshrc`:**
```bash
# Change:
alias yt-collect='python collect_comprehensive_fixed.py --sources data/sources.csv'
alias yt-collect-resume='python collect_comprehensive_fixed.py --sources data/sources.csv --resume'
alias yt-collect-test='python collect_comprehensive_fixed.py --sources data/sources.csv --max-channels 3'

# To:
alias yt-collect='python collect.py --sources data/sources.csv'
alias yt-collect-resume='python collect.py --sources data/sources.csv --resume'
alias yt-collect-test='python collect.py --sources data/sources.csv --max-channels 3'
```

### Step 7: Update .gitignore (if needed)

Ensure no references to old filenames that might cause confusion.

### Step 8: Test Everything

```bash
# Test basic collection
python collect.py --sources data/sources.csv --max-channels 1

# Test with different config
python collect.py --sources data/sources.csv --max-channels 1 --config config/config.yaml

# Test resume functionality
python collect.py --sources data/sources.csv --resume

# Test shell scripts
bash status.sh
bash auto_resume.sh
```

### Step 9: Commit Changes

```bash
git add .
git commit -m "Refactor: Consolidate collectors into single collect.py

- Rename collect_comprehensive_fixed.py → collect.py
- Remove deprecated collectors (collect_comprehensive.py, run_collector.py, src/collector.py)
- Update all shell scripts to use collect.py
- Update all documentation (README, CLAUDE.md, DEPLOYMENT.md)
- Update terminal aliases

Breaking changes:
- Main entry point is now: python collect.py
- Old scripts removed, will cause errors if referenced

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Step 10: Merge to Main and Production

```bash
# Test on refactor branch first
python collect.py --sources data/sources.csv --max-channels 2

# If successful, merge to main
git checkout main
git merge refactor-collectors

# Push to GitHub
git push origin main

# Update production (when ready)
git checkout production
git merge main
git push origin production
```

## Alternative: Minimal Fix Strategy

If you prefer to keep the current structure temporarily:

### Quick Fix Option

Just update references without removing files:

1. **Update `auto_resume.sh` and `status.sh`** to use `collect_comprehensive_fixed.py`
2. **Update aliases** to use `collect_comprehensive_fixed.py`
3. **Add note in README** that the main script is `collect_comprehensive_fixed.py`

This is less clean but requires minimal changes.

## Recommended Directory Structure (After Refactoring)

```
youtube_monitoring_pipeline/
├── collect.py                    # Main entry point (comprehensive collector)
├── view_data.py                  # Data inspection
├── test_api_quick.py            # API testing
├── download_captions.py         # Caption utilities
├── download_transcripts.py      # Transcript utilities
├── auto_resume.sh               # Auto-resume script
├── status.sh                    # Status checker
├── config/
│   ├── config.yaml.template           # Development config template
│   └── config_comprehensive.yaml.template  # Production config template
├── src/
│   ├── youtube_client.py        # API wrapper
│   ├── database.py              # Database layer
│   └── utils/
│       └── helpers.py           # Utility functions
├── data/                        # Data directory
├── logs/                        # Log directory
└── tests/                       # Unit tests (future)
```

## Benefits of Refactoring

1. **Single Source of Truth**: One entry point, no confusion
2. **Standard Naming**: `collect.py` is intuitive
3. **Easier Documentation**: One command to document
4. **Easier Maintenance**: No duplicate code
5. **Better Onboarding**: New users won't be confused
6. **Cleaner Git History**: Remove dead code

## Risks and Mitigation

| Risk | Mitigation |
|------|------------|
| Breaking existing workflows | Test thoroughly on refactor branch first |
| Server automation breaks | Update cron jobs before merging to production |
| Lost functionality | Verify all features work in renamed script |
| Documentation out of sync | Update all docs in single commit |

## Timeline Recommendation

- **Phase 1-2**: 30 minutes (rename and remove files)
- **Phase 3**: 30 minutes (update documentation)
- **Phase 4**: 15 minutes (testing)
- **Total**: ~1.5 hours

## Decision Point

**Choose one:**

1. ✅ **Full Refactor** (Recommended): Clean, maintainable, standard naming
2. ⚠️ **Minimal Fix**: Quick update of references, keep all files

Which approach would you like to take?
