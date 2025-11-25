#!/usr/bin/env python3
"""
Migrate database to add quota tracking improvements
"""
import sqlite3
from datetime import datetime

def migrate_database():
    """Add quota tracking improvements to existing database"""
    print("Migrating Database for Quota Fix")
    print("=" * 60)

    conn = sqlite3.connect('data/youtube_monitoring.db')
    cursor = conn.cursor()

    # 1. Check and add quota_cumulative column to collection_runs
    print("\n1. Checking collection_runs table...")
    cursor.execute("PRAGMA table_info(collection_runs)")
    columns = [col[1] for col in cursor.fetchall()]

    if 'quota_cumulative' not in columns:
        print("   Adding quota_cumulative column...")
        cursor.execute("""
            ALTER TABLE collection_runs
            ADD COLUMN quota_cumulative INTEGER DEFAULT 0
        """)
        conn.commit()
        print("   ✓ quota_cumulative column added")
    else:
        print("   ✓ quota_cumulative column already exists")

    # 2. Create quota_tracking table
    print("\n2. Checking quota_tracking table...")
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='quota_tracking'
    """)

    if not cursor.fetchone():
        print("   Creating quota_tracking table...")
        cursor.execute("""
            CREATE TABLE quota_tracking (
                track_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER,
                timestamp TEXT,
                api_method TEXT,
                quota_cost INTEGER,
                details TEXT,
                FOREIGN KEY (run_id) REFERENCES collection_runs (run_id)
            )
        """)

        # Create index for better performance
        cursor.execute("""
            CREATE INDEX idx_quota_tracking_run
            ON quota_tracking(run_id)
        """)

        conn.commit()
        print("   ✓ quota_tracking table created")
    else:
        print("   ✓ quota_tracking table already exists")

    # 3. Estimate and backfill cumulative quota for existing runs
    print("\n3. Estimating cumulative quota for existing runs...")
    cursor.execute("""
        SELECT run_id, channels_processed, videos_collected, comments_collected, quota_used
        FROM collection_runs
        WHERE status IN ('completed', 'interrupted')
        ORDER BY run_id
    """)

    runs = cursor.fetchall()
    cumulative = 0

    for run_id, channels, videos, comments, reported_quota in runs:
        if channels and videos and comments:
            # Estimate actual quota based on the data collected
            # This is a conservative estimate
            estimated_quota = (
                channels * 2 +           # Channel info + initial queries
                (videos // 50) * 1 +     # Video list pages
                (videos // 50) * 1 +     # Video details batches
                (comments // 100) * 1    # Comment pages
            )

            # Use the maximum of reported and estimated
            actual_quota = max(reported_quota or 0, estimated_quota)
            cumulative += actual_quota

            # Update the record
            cursor.execute("""
                UPDATE collection_runs
                SET quota_cumulative = ?
                WHERE run_id = ?
            """, (cumulative, run_id))

            print(f"   Run {run_id}: {channels} channels, {videos} videos, {comments} comments")
            print(f"      Reported: {reported_quota or 0}, Estimated: {estimated_quota}, Cumulative: {cumulative}")

    conn.commit()
    print(f"\n   ✓ Updated {len(runs)} collection runs with cumulative quota")

    # 4. Show summary
    print("\n" + "=" * 60)
    print("Migration Summary:")
    print("-" * 60)

    cursor.execute("""
        SELECT COUNT(*) as total_runs,
               MAX(quota_cumulative) as max_cumulative,
               SUM(videos_collected) as total_videos,
               SUM(comments_collected) as total_comments
        FROM collection_runs
        WHERE status IN ('completed', 'interrupted')
    """)

    result = cursor.fetchone()
    if result:
        total_runs, max_cumulative, total_videos, total_comments = result
        print(f"Total collection runs: {total_runs}")
        print(f"Total videos collected: {total_videos:,}")
        print(f"Total comments collected: {total_comments:,}")
        print(f"Estimated cumulative quota: {max_cumulative:,} units")

    conn.close()
    print("\n✓ Database migration completed successfully!")
    print("\nNOTE: The quota tracking fix is now ready to use.")
    print("Future collection runs will track quota accurately.")

if __name__ == "__main__":
    migrate_database()