#!/bin/bash
# Auto-resume script for daily quota resets
# Runs automatically via crontab

cd ~/Documents/Youtube/youtube_monitoring_pipeline
source venv/bin/activate

LOG_FILE="logs/auto_resume_$(date +%Y%m%d).log"

echo "==========================================" >> $LOG_FILE
echo "Auto-resume started at $(date)" >> $LOG_FILE
echo "==========================================" >> $LOG_FILE

# Check if collection is already running
if pgrep -f "collect_comprehensive" > /dev/null; then
    echo "Collection already running, skipping" >> $LOG_FILE
    echo "PID: $(pgrep -f collect_comprehensive)" >> $LOG_FILE
    exit 0
fi

# Check if there's a checkpoint (meaning collection isn't complete)
if [ -f "data/checkpoints/latest_checkpoint.json" ]; then
    echo "Checkpoint found, resuming collection" >> $LOG_FILE
    
    # Get checkpoint info
    CHANNEL_INDEX=$(grep -o '"channel_index": [0-9]*' data/checkpoints/latest_checkpoint.json | grep -o '[0-9]*')
    echo "Resuming from channel: $CHANNEL_INDEX" >> $LOG_FILE
    
    # Start in detached screen session
    screen -dmS youtube_collection bash -c "
        cd ~/Documents/Youyube/youtube_monitoring_pipeline
        source venv/bin/activate
        python3 collect_comprehensive_fixed.py --sources data/sources.csv --resume >> $LOG_FILE 2>&1
    "
    
    echo "Collection resumed in screen session 'youtube_collection'" >> $LOG_FILE
    echo "View with: screen -r youtube_collection" >> $LOG_FILE
else
    echo "No checkpoint found - collection may be complete!" >> $LOG_FILE
    
    # Check if we ever started
    if [ -f "data/youtube_monitoring.db" ]; then
        CHANNEL_COUNT=$(sqlite3 data/youtube_monitoring.db "SELECT COUNT(*) FROM channels;" 2>/dev/null)
        echo "Channels in database: $CHANNEL_COUNT" >> $LOG_FILE
        
        if [ "$CHANNEL_COUNT" -lt 12000 ]; then
            echo "WARNING: Low channel count but no checkpoint - collection may have failed" >> $LOG_FILE
        else
            echo "Collection appears complete!" >> $LOG_FILE
        fi
    else
        echo "No database found - collection never started" >> $LOG_FILE
    fi
fi

echo "Auto-resume finished at $(date)" >> $LOG_FILE
echo "==========================================" >> $LOG_FILE
echo "" >> $LOG_FILE
