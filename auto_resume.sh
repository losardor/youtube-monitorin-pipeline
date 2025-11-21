#!/bin/bash
# Auto-resume script for daily quota resets
# Place in: ~/youtube_monitoring_pipeline/auto_resume.sh

cd ~/youtube_monitoring_pipeline
source venv/bin/activate

LOG_FILE="logs/auto_resume_$(date +%Y%m%d).log"

echo "==================================" >> $LOG_FILE
echo "Auto-resume started at $(date)" >> $LOG_FILE
echo "==================================" >> $LOG_FILE

# Check if collection is already running
if pgrep -f "collect_comprehensive.py" > /dev/null; then
    echo "Collection already running, skipping" >> $LOG_FILE
    exit 0
fi

# Check if there's a checkpoint (meaning collection isn't complete)
if [ -f "data/checkpoints/latest_checkpoint.json" ]; then
    echo "Checkpoint found, resuming collection" >> $LOG_FILE
    
    # Start in detached screen session
    screen -dmS youtube_collection bash -c "
        cd ~/youtube_monitoring_pipeline
        source venv/bin/activate
        python collect_comprehensive.py --sources data/sources.csv --resume >> $LOG_FILE 2>&1
    "
    
    echo "Collection resumed in screen session 'youtube_collection'" >> $LOG_FILE
else
    echo "No checkpoint found, collection may be complete" >> $LOG_FILE
fi

echo "Auto-resume finished at $(date)" >> $LOG_FILE
