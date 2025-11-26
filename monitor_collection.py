#!/usr/bin/env python3
"""
Real-time Collection Monitor for YouTube Monitoring Pipeline
Run this script in a separate terminal to monitor ongoing collection.
"""

import os
import sys
import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path
import argparse

class CollectionMonitor:
    def __init__(self, refresh_interval=5):
        self.refresh_interval = refresh_interval
        self.db_path = 'data/youtube_monitoring.db'
        self.checkpoint_path = 'data/checkpoints/latest_checkpoint.json'
        self.log_path = 'logs/pipeline.log'
        self.last_log_size = 0
        self.production_quota_limit = 1000000
        self.quota_buffer = 50000

    def clear_screen(self):
        """Clear terminal screen"""
        os.system('clear' if os.name == 'posix' else 'cls')

    def format_number(self, num):
        """Format number with thousands separator"""
        if num is None:
            return "N/A"
        return f"{num:,}"

    def format_time_ago(self, timestamp_str):
        """Format timestamp as 'X minutes ago'"""
        if not timestamp_str:
            return "N/A"

        try:
            timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            now = datetime.now()
            diff = now - timestamp.replace(tzinfo=None)

            if diff.total_seconds() < 60:
                return f"{int(diff.total_seconds())}s ago"
            elif diff.total_seconds() < 3600:
                return f"{int(diff.total_seconds() / 60)}m ago"
            elif diff.total_seconds() < 86400:
                return f"{int(diff.total_seconds() / 3600)}h ago"
            else:
                return f"{int(diff.total_seconds() / 86400)}d ago"
        except:
            return timestamp_str

    def get_database_stats(self):
        """Get current statistics from database"""
        stats = {
            'total_channels': 0,
            'total_videos': 0,
            'total_comments': 0,
            'current_run': None,
            'last_run': None
        }

        if not Path(self.db_path).exists():
            return stats

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Get totals
            cursor.execute("SELECT COUNT(*) FROM channels")
            stats['total_channels'] = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM videos")
            stats['total_videos'] = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM comments")
            stats['total_comments'] = cursor.fetchone()[0]

            # Get current running collection
            cursor.execute("""
                SELECT run_id, start_time, channels_processed, videos_collected,
                       comments_collected, quota_used, quota_cumulative, status
                FROM collection_runs
                WHERE status = 'running'
                ORDER BY run_id DESC
                LIMIT 1
            """)
            current = cursor.fetchone()
            if current:
                stats['current_run'] = {
                    'run_id': current[0],
                    'start_time': current[1],
                    'channels_processed': current[2],
                    'videos_collected': current[3],
                    'comments_collected': current[4],
                    'quota_used': current[5],
                    'quota_cumulative': current[6],
                    'status': current[7]
                }

            # Get last completed collection
            cursor.execute("""
                SELECT run_id, start_time, end_time, channels_processed,
                       videos_collected, comments_collected, quota_used, quota_cumulative, status
                FROM collection_runs
                WHERE status IN ('completed', 'interrupted')
                ORDER BY run_id DESC
                LIMIT 1
            """)
            last = cursor.fetchone()
            if last:
                stats['last_run'] = {
                    'run_id': last[0],
                    'start_time': last[1],
                    'end_time': last[2],
                    'channels_processed': last[3],
                    'videos_collected': last[4],
                    'comments_collected': last[5],
                    'quota_used': last[6],
                    'quota_cumulative': last[7],
                    'status': last[8]
                }

            conn.close()

        except Exception as e:
            print(f"Database error: {e}")

        return stats

    def get_checkpoint_info(self):
        """Get current checkpoint information"""
        if not Path(self.checkpoint_path).exists():
            return None

        try:
            with open(self.checkpoint_path, 'r') as f:
                return json.load(f)
        except:
            return None

    def get_recent_logs(self, num_lines=10):
        """Get recent log lines"""
        if not Path(self.log_path).exists():
            return []

        try:
            with open(self.log_path, 'r') as f:
                lines = f.readlines()
                return lines[-num_lines:]
        except:
            return []

    def calculate_rate(self, count, start_time):
        """Calculate processing rate per hour"""
        if not count or not start_time:
            return 0

        try:
            start = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            now = datetime.now()
            hours = (now - start.replace(tzinfo=None)).total_seconds() / 3600
            if hours > 0:
                return int(count / hours)
            return 0
        except:
            return 0

    def display_dashboard(self):
        """Display monitoring dashboard"""
        self.clear_screen()

        # Header
        print("="*80)
        print(" YOUTUBE COLLECTION MONITOR")
        print(" Updated:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        print("="*80)

        # Get current data
        stats = self.get_database_stats()
        checkpoint = self.get_checkpoint_info()

        # Database Totals
        print("\n📊 DATABASE TOTALS")
        print("-"*40)
        print(f"  Channels:  {self.format_number(stats['total_channels'])}")
        print(f"  Videos:    {self.format_number(stats['total_videos'])}")
        print(f"  Comments:  {self.format_number(stats['total_comments'])}")

        # Current Collection Run
        if stats['current_run']:
            run = stats['current_run']
            print("\n🔄 CURRENT COLLECTION (RUNNING)")
            print("-"*40)
            print(f"  Run ID:      {run['run_id']}")
            print(f"  Started:     {self.format_time_ago(run['start_time'])}")
            print(f"  Channels:    {self.format_number(run['channels_processed'])}")
            print(f"  Videos:      {self.format_number(run['videos_collected'])}")
            print(f"  Comments:    {self.format_number(run['comments_collected'])}")

            # Quota information
            print(f"\n  📊 QUOTA STATUS")
            session_quota = run['quota_used'] or 0
            cumulative_quota = run['quota_cumulative'] or 0

            print(f"  Session:     {self.format_number(session_quota)} units")
            print(f"  Cumulative:  {self.format_number(cumulative_quota)} units")

            # Quota progress bar
            quota_percent = (cumulative_quota / self.production_quota_limit) * 100
            bar_length = 40
            filled = int(bar_length * quota_percent / 100)
            bar = '█' * filled + '░' * (bar_length - filled)

            print(f"  Progress:    [{bar}] {quota_percent:.1f}%")

            remaining = self.production_quota_limit - cumulative_quota - self.quota_buffer
            if remaining > 0:
                print(f"  Remaining:   {self.format_number(remaining)} units (before buffer)")
            else:
                print(f"  ⚠️  WARNING: Approaching quota limit!")

            # Processing rates
            rate_channels = self.calculate_rate(run['channels_processed'], run['start_time'])
            rate_videos = self.calculate_rate(run['videos_collected'], run['start_time'])
            rate_comments = self.calculate_rate(run['comments_collected'], run['start_time'])

            print(f"\n  ⚡ PROCESSING RATES (per hour)")
            print(f"  Channels:    {self.format_number(rate_channels)}/h")
            print(f"  Videos:      {self.format_number(rate_videos)}/h")
            print(f"  Comments:    {self.format_number(rate_comments)}/h")

        else:
            print("\n⏸️  NO ACTIVE COLLECTION")

        # Checkpoint Information
        if checkpoint:
            print("\n💾 LAST CHECKPOINT")
            print("-"*40)
            print(f"  Channel Index:   {checkpoint.get('channel_index', 0)}")
            print(f"  Channels Done:   {checkpoint.get('channels_processed', 0)}")
            print(f"  Last Update:     {self.format_time_ago(checkpoint.get('timestamp'))}")

        # Last Completed Run
        if stats['last_run']:
            last = stats['last_run']
            print("\n✅ LAST COMPLETED RUN")
            print("-"*40)
            print(f"  Run ID:      {last['run_id']}")
            print(f"  Status:      {last['status'].upper()}")
            print(f"  Ended:       {self.format_time_ago(last['end_time'])}")
            print(f"  Channels:    {self.format_number(last['channels_processed'])}")
            print(f"  Videos:      {self.format_number(last['videos_collected'])}")
            print(f"  Comments:    {self.format_number(last['comments_collected'])}")
            print(f"  Quota Used:  {self.format_number(last['quota_used'])} units")

        # Recent Log Activity
        print("\n📝 RECENT LOG ACTIVITY")
        print("-"*40)
        logs = self.get_recent_logs(5)
        for log in logs:
            # Truncate long lines
            log = log.strip()[:75]
            if log:
                print(f"  {log}")

        # Footer
        print("\n" + "="*80)
        print(f"Refreshing every {self.refresh_interval} seconds... Press Ctrl+C to stop")

    def run(self):
        """Run the monitor"""
        try:
            while True:
                self.display_dashboard()
                time.sleep(self.refresh_interval)
        except KeyboardInterrupt:
            print("\n\n✋ Monitor stopped by user")
            sys.exit(0)

def main():
    parser = argparse.ArgumentParser(description='Monitor YouTube collection in real-time')
    parser.add_argument(
        '--refresh',
        type=int,
        default=5,
        help='Refresh interval in seconds (default: 5)'
    )

    args = parser.parse_args()

    monitor = CollectionMonitor(refresh_interval=args.refresh)
    monitor.run()

if __name__ == "__main__":
    main()