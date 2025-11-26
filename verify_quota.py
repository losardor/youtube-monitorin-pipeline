#!/usr/bin/env python3
"""
Quota Calculation and Verification Script
Validates quota tracking accuracy and provides detailed analysis.
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import sys

class QuotaVerifier:
    def __init__(self):
        self.db_path = 'data/youtube_monitoring.db'
        self.checkpoint_path = 'data/checkpoints/latest_checkpoint.json'

        # YouTube API v3 Quota Costs (units)
        self.QUOTA_COSTS = {
            'search': 100,                    # Search for channels
            'channels.list': 1,                # Get channel details
            'playlistItems.list': 1,           # List videos from playlist
            'videos.list': 1,                  # Get video details (batch)
            'commentThreads.list': 1,          # List comments
            'comments.list': 1,                # List comment replies
            'captions.list': 50,               # List caption tracks
        }

        self.QUOTA_LIMIT = 1000000  # Production quota limit
        self.QUOTA_BUFFER = 50000   # Safety buffer

    def print_header(self, text):
        print(f"\n{'='*60}")
        print(f" {text}")
        print('='*60)

    def format_number(self, num):
        if num is None:
            return "N/A"
        return f"{num:,}"

    def analyze_database_quota(self):
        """Analyze quota tracking in database"""
        self.print_header("DATABASE QUOTA ANALYSIS")

        if not Path(self.db_path).exists():
            print("❌ Database not found!")
            return

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get all collection runs
        cursor.execute("""
            SELECT run_id, start_time, end_time, status,
                   channels_processed, videos_collected, comments_collected,
                   quota_used, quota_cumulative
            FROM collection_runs
            ORDER BY run_id DESC
            LIMIT 10
        """)

        runs = cursor.fetchall()

        print("\n📊 Collection Runs Summary:")
        print("-"*60)
        print(f"{'ID':>4} {'Status':<12} {'Channels':>10} {'Quota Used':>12} {'Cumulative':>12}")
        print("-"*60)

        for run in runs:
            run_id, start, end, status, channels, videos, comments, quota, cumulative = run
            print(f"{run_id:>4} {status:<12} {channels:>10} {self.format_number(quota):>12} {self.format_number(cumulative):>12}")

        # Verify quota continuity
        self.print_header("QUOTA CONTINUITY CHECK")

        cursor.execute("""
            SELECT run_id, quota_cumulative,
                   quota_cumulative - LAG(quota_cumulative) OVER (ORDER BY run_id) as calculated_session,
                   quota_used
            FROM collection_runs
            WHERE quota_cumulative IS NOT NULL
            ORDER BY run_id
        """)

        continuity = cursor.fetchall()

        errors = []
        for row in continuity:
            run_id, cumulative, calculated, reported = row
            if calculated is not None and reported is not None:
                diff = abs(calculated - reported)
                if diff > 10:  # Allow small discrepancies
                    errors.append((run_id, calculated, reported, diff))

        if errors:
            print("⚠️  Quota discrepancies found:")
            for run_id, calc, rep, diff in errors:
                print(f"  Run {run_id}: Calculated={calc:,}, Reported={rep:,}, Diff={diff:,}")
        else:
            print("✅ Quota continuity verified - All runs consistent!")

        # Analyze quota by API method
        self.print_header("QUOTA BY API METHOD")

        cursor.execute("""
            SELECT api_method, COUNT(*) as calls, SUM(quota_cost) as total
            FROM quota_tracking
            WHERE run_id = (SELECT MAX(run_id) FROM collection_runs)
            GROUP BY api_method
            ORDER BY total DESC
        """)

        api_usage = cursor.fetchall()

        if api_usage:
            print(f"\n{'API Method':<25} {'Calls':>10} {'Total Quota':>12}")
            print("-"*50)
            total_quota = 0
            for method, calls, quota in api_usage:
                print(f"{method:<25} {calls:>10} {quota:>12,}")
                total_quota += quota

            print("-"*50)
            print(f"{'TOTAL':<25} {sum(c for _, c, _ in api_usage):>10} {total_quota:>12,}")
        else:
            print("No quota tracking data found for latest run")

        conn.close()

    def calculate_expected_quota(self):
        """Calculate expected quota based on collection data"""
        self.print_header("EXPECTED QUOTA CALCULATION")

        if not Path(self.db_path).exists():
            print("❌ Database not found!")
            return

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get collection statistics
        cursor.execute("""
            SELECT
                COUNT(DISTINCT channel_id) as channels,
                COUNT(DISTINCT video_id) as videos,
                COUNT(DISTINCT comment_id) as comments
            FROM channels
            LEFT JOIN videos USING(channel_id)
            LEFT JOIN comments USING(video_id)
        """)

        stats = cursor.fetchone()
        if not stats:
            print("No data found in database")
            return

        channels, videos, comments = stats

        print(f"\n📈 Collection Statistics:")
        print(f"  Channels:  {self.format_number(channels)}")
        print(f"  Videos:    {self.format_number(videos)}")
        print(f"  Comments:  {self.format_number(comments)}")

        # Calculate expected quota
        print(f"\n💰 Expected Quota Calculation:")

        # Base costs
        channel_quota = channels * 1  # Channel info
        video_list_quota = (videos // 50 + 1) * 1  # Paginated lists
        video_detail_quota = (videos // 50 + 1) * 1  # Batch details
        comment_quota = (comments // 100 + 1) * 1  # Comment pages

        print(f"  Channel lookups:    {channels:>8} × 1    = {channel_quota:>10,} units")
        print(f"  Video list pages:   {videos//50 + 1:>8} × 1    = {video_list_quota:>10,} units")
        print(f"  Video detail batch: {videos//50 + 1:>8} × 1    = {video_detail_quota:>10,} units")
        print(f"  Comment pages:      {comments//100 + 1:>8} × 1    = {comment_quota:>10,} units")

        total_expected = channel_quota + video_list_quota + video_detail_quota + comment_quota

        print("-"*50)
        print(f"  Total Expected:                        {total_expected:>10,} units")

        # Compare with actual
        cursor.execute("SELECT MAX(quota_cumulative) FROM collection_runs")
        actual = cursor.fetchone()[0]

        if actual:
            print(f"  Actual Cumulative:                     {actual:>10,} units")
            difference = actual - total_expected
            percentage = (actual / total_expected * 100) if total_expected > 0 else 0

            print(f"  Difference:                            {difference:>10,} units")
            print(f"  Accuracy:                              {percentage:>9.1f}%")

            if abs(difference) > total_expected * 0.1:  # More than 10% difference
                print("\n⚠️  Significant difference detected!")
                print("  Possible reasons:")
                print("  - Additional API calls for error handling")
                print("  - Caption track queries (50 units each)")
                print("  - Retry attempts on failures")
                print("  - Channel ID resolution queries")
            else:
                print("\n✅ Quota tracking is accurate!")

        conn.close()

    def analyze_checkpoint(self):
        """Analyze checkpoint file"""
        self.print_header("CHECKPOINT ANALYSIS")

        if not Path(self.checkpoint_path).exists():
            print("No checkpoint file found")
            return

        with open(self.checkpoint_path, 'r') as f:
            checkpoint = json.load(f)

        print(f"\n📍 Checkpoint Status:")
        print(f"  Timestamp:         {checkpoint.get('timestamp', 'N/A')}")
        print(f"  Channel Index:     {checkpoint.get('channel_index', 0)}")
        print(f"  Channels Done:     {checkpoint.get('channels_processed', 0)}")
        print(f"  Session Quota:     {self.format_number(checkpoint.get('quota_usage', 0))}")
        print(f"  Cumulative Quota:  {self.format_number(checkpoint.get('quota_cumulative', 0))}")

        cumulative = checkpoint.get('quota_cumulative', 0)
        remaining = self.QUOTA_LIMIT - cumulative - self.QUOTA_BUFFER

        print(f"\n💡 Quota Status:")
        print(f"  Used:      {self.format_number(cumulative)} / {self.format_number(self.QUOTA_LIMIT)}")
        print(f"  Remaining: {self.format_number(remaining)} (before buffer)")
        print(f"  Progress:  {cumulative/self.QUOTA_LIMIT*100:.1f}%")

        if remaining <= 0:
            print("\n⚠️  WARNING: Quota limit reached or exceeded!")
            print("  Collection will stop to prevent quota violations")

    def project_quota_needs(self):
        """Project quota needs for remaining collection"""
        self.print_header("QUOTA PROJECTION")

        if not Path(self.db_path).exists():
            print("❌ Database not found!")
            return

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get average quota per channel
        cursor.execute("""
            SELECT
                AVG(quota_used * 1.0 / NULLIF(channels_processed, 0)) as avg_per_channel,
                MAX(quota_cumulative) as current_total
            FROM collection_runs
            WHERE channels_processed > 0 AND quota_used IS NOT NULL
        """)

        result = cursor.fetchone()
        if not result or result[0] is None:
            print("Insufficient data for projection")
            conn.close()
            return

        avg_quota_per_channel = result[0]
        current_cumulative = result[1] or 0

        # Get total channels to process
        cursor.execute("SELECT COUNT(*) FROM channels")
        total_channels = cursor.fetchone()[0]

        # Get already processed channels
        cursor.execute("SELECT COUNT(*) FROM channels WHERE collection_date IS NOT NULL")
        processed_channels = cursor.fetchone()[0]

        remaining_channels = total_channels - processed_channels

        print(f"\n📊 Collection Progress:")
        print(f"  Total Channels:      {self.format_number(total_channels)}")
        print(f"  Processed:           {self.format_number(processed_channels)}")
        print(f"  Remaining:           {self.format_number(remaining_channels)}")

        print(f"\n💰 Quota Projection:")
        print(f"  Avg per Channel:     {avg_quota_per_channel:.1f} units")
        print(f"  Current Cumulative:  {self.format_number(current_cumulative)} units")

        projected_quota_needed = remaining_channels * avg_quota_per_channel
        total_quota_needed = current_cumulative + projected_quota_needed

        print(f"  Projected Need:      {self.format_number(int(projected_quota_needed))} units")
        print(f"  Total Expected:      {self.format_number(int(total_quota_needed))} units")

        days_needed = total_quota_needed / (self.QUOTA_LIMIT - self.QUOTA_BUFFER)

        print(f"\n⏱️  Time Estimate:")
        print(f"  Days Needed:         {days_needed:.1f} days")

        if days_needed > 1:
            print(f"  Strategy:            Collection will span multiple days")
            print(f"  Use --resume flag to continue across quota resets")
        else:
            print(f"  Strategy:            Should complete within daily quota")

        # Channels per day calculation
        channels_per_day = (self.QUOTA_LIMIT - self.QUOTA_BUFFER) / avg_quota_per_channel
        print(f"  Channels/Day:        {int(channels_per_day)} channels")

        conn.close()

    def verify_quota_implementation(self):
        """Verify quota tracking implementation"""
        self.print_header("IMPLEMENTATION VERIFICATION")

        # Check if required files exist
        files_to_check = [
            ('collect.py', 'Main collector script'),
            ('src/youtube_client.py', 'YouTube API client'),
            ('src/database.py', 'Database handler'),
            ('check_quota_bug.py', 'Quota verification script'),
            ('test_quota_fix.py', 'Quota test script'),
        ]

        print("\n📁 File Verification:")
        for filepath, description in files_to_check:
            if Path(filepath).exists():
                print(f"  ✅ {filepath:<30} - {description}")
            else:
                print(f"  ❌ {filepath:<30} - {description}")

        # Check for quota tracking in code
        print("\n🔍 Code Implementation Check:")

        if Path('src/youtube_client.py').exists():
            with open('src/youtube_client.py', 'r') as f:
                content = f.read()

            checks = [
                ('quota_usage tracking', 'self.quota_usage' in content),
                ('quota_cumulative tracking', 'self.quota_cumulative' in content),
                ('_track_quota method', '_track_quota' in content),
                ('Quota persistence', 'quota_cumulative' in content),
            ]

            for feature, present in checks:
                if present:
                    print(f"  ✅ {feature}")
                else:
                    print(f"  ❌ {feature} - May need implementation")

    def generate_report(self):
        """Generate comprehensive quota report"""
        self.print_header("QUOTA VERIFICATION REPORT")
        print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # Run all analyses
        self.analyze_database_quota()
        self.calculate_expected_quota()
        self.analyze_checkpoint()
        self.project_quota_needs()
        self.verify_quota_implementation()

        # Final recommendations
        self.print_header("RECOMMENDATIONS")

        recommendations = []

        # Check database
        if Path(self.db_path).exists():
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Check quota_cumulative column
            cursor.execute("PRAGMA table_info(collection_runs)")
            columns = {row[1] for row in cursor.fetchall()}

            if 'quota_cumulative' not in columns:
                recommendations.append("Run check_quota_bug.py to add quota_cumulative column")

            # Check current quota usage
            cursor.execute("SELECT MAX(quota_cumulative) FROM collection_runs")
            current = cursor.fetchone()[0] or 0

            if current > self.QUOTA_LIMIT - self.QUOTA_BUFFER:
                recommendations.append("Quota near limit - wait for daily reset before continuing")
            elif current > self.QUOTA_LIMIT * 0.8:
                recommendations.append("Quota usage high - monitor closely")

            conn.close()

        # Check checkpoint
        if Path(self.checkpoint_path).exists():
            recommendations.append("Checkpoint exists - use --resume flag to continue")

        if recommendations:
            print("\n⚠️  Action Items:")
            for i, rec in enumerate(recommendations, 1):
                print(f"  {i}. {rec}")
        else:
            print("\n✅ System ready for production collection!")
            print("\nStart with:")
            print("  python collect.py --sources data/sources.csv")

def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Verify quota tracking and calculations')
    parser.add_argument('--report', action='store_true', help='Generate full report')
    parser.add_argument('--database', action='store_true', help='Analyze database quota only')
    parser.add_argument('--checkpoint', action='store_true', help='Analyze checkpoint only')
    parser.add_argument('--projection', action='store_true', help='Project quota needs')

    args = parser.parse_args()

    verifier = QuotaVerifier()

    if args.report or not any([args.database, args.checkpoint, args.projection]):
        verifier.generate_report()
    else:
        if args.database:
            verifier.analyze_database_quota()
        if args.checkpoint:
            verifier.analyze_checkpoint()
        if args.projection:
            verifier.project_quota_needs()

if __name__ == "__main__":
    main()