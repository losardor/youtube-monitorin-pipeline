#!/bin/bash
# Quick status check
# Save as: ~/youtube_monitoring_pipeline/status.sh

cd ~/youtube_monitoring_pipeline
source venv/bin/activate

echo "=========================================="
echo "YouTube Collection Status"
echo "=========================================="
echo ""

# Check if running
if pgrep -f "collect.py" > /dev/null; then
    echo "✓ Collection is RUNNING"
    PID=$(pgrep -f "collect.py")
    echo "  Process ID: $PID"
    echo "  Runtime: $(ps -p $PID -o etime= | tr -d ' ')"
    echo ""
    
    # Show recent log
    echo "Last 3 channels processed:"
    tail -30 logs/pipeline.log | grep "^\[" | tail -3
    echo ""
    
    # Show quota
    echo "Quota status:"
    tail -50 logs/pipeline.log | grep "Quota used" | tail -1
else
    echo "✗ Collection is NOT running"
    echo ""
    
    # Check if there's a checkpoint
    if [ -f "data/checkpoints/latest_checkpoint.json" ]; then
        echo "⚠ Checkpoint exists - collection was paused"
        echo "  Resume with: python collect.py --resume"
    else
        echo "✓ No checkpoint found - may be complete or never started"
    fi
fi

echo ""
echo "Database stats:"
python3 << 'PYEOF'
from src.database import Database
db = Database('data/youtube_monitoring.db')
cursor = db.conn.cursor()

cursor.execute('SELECT COUNT(*) FROM channels')
channels = cursor.fetchone()[0]

cursor.execute('SELECT COUNT(*) FROM videos')
videos = cursor.fetchone()[0]

cursor.execute('SELECT COUNT(*) FROM comments')
comments = cursor.fetchone()[0]

cursor.execute('SELECT SUM(quota_used) FROM collection_runs WHERE DATE(start_time) = DATE("now", "localtime")')
today_quota = cursor.fetchone()[0] or 0

print(f"  Channels: {channels:,}")
print(f"  Videos: {videos:,}")
print(f"  Comments: {comments:,}")
print(f"  Today's quota: {today_quota:,} units")

db.close()
PYEOF

echo ""
echo "=========================================="
