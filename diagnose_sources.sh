#!/bin/bash
cd ~/youtube_monitoring_pipeline

echo "=== SOURCE DIAGNOSTICS ==="
echo ""

echo "1. Total sources in CSV:"
wc -l data/sources.csv

echo ""
echo "2. Sample URLs (first 10):"
head -10 data/sources.csv

echo ""
echo "3. Common failure reasons from logs:"
grep "✗" logs/pipeline.log | tail -100 | cut -d':' -f2- | sort | uniq -c | sort -rn | head -10

echo ""
echo "4. Successful channels today:"
sqlite3 data/youtube_monitoring.db "SELECT COUNT(*) FROM channels WHERE DATE(collected_at) = DATE('now', 'localtime');"

echo ""
echo "5. Failed extractions:"
grep "Could not extract channel ID" logs/pipeline.log | wc -l

echo ""
echo "6. Failed retrievals:"
grep "Could not retrieve channel info" logs/pipeline.log | wc -l

echo ""
echo "=== END DIAGNOSTICS ==="
