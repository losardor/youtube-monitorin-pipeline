#!/usr/bin/env python3
"""
Production Verification Script for YouTube Monitoring Pipeline
Run this script to verify the system is ready for production data collection.
"""

import os
import sys
import json
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path
import time
import yaml

class ProductionVerifier:
    def __init__(self):
        self.checks_passed = []
        self.checks_failed = []
        self.warnings = []

    def print_header(self, text):
        """Print a formatted header"""
        print(f"\n{'='*60}")
        print(f" {text}")
        print('='*60)

    def print_success(self, text):
        """Print success message"""
        print(f"✅ {text}")
        self.checks_passed.append(text)

    def print_error(self, text):
        """Print error message"""
        print(f"❌ {text}")
        self.checks_failed.append(text)

    def print_warning(self, text):
        """Print warning message"""
        print(f"⚠️  {text}")
        self.warnings.append(text)

    def print_info(self, text):
        """Print info message"""
        print(f"ℹ️  {text}")

    def check_environment(self):
        """Check Python environment and dependencies"""
        self.print_header("ENVIRONMENT CHECKS")

        # Check Python version
        python_version = sys.version_info
        if python_version.major >= 3 and python_version.minor >= 8:
            self.print_success(f"Python version: {python_version.major}.{python_version.minor}.{python_version.micro}")
        else:
            self.print_error(f"Python version {python_version.major}.{python_version.minor} is too old. Requires 3.8+")

        # Check required packages
        required_packages = [
            'google-api-python-client',
            'python-dotenv',
            'pandas',
            'pyyaml'
        ]

        for package in required_packages:
            try:
                __import__(package.replace('-', '_'))
                self.print_success(f"Package '{package}' is installed")
            except ImportError:
                self.print_error(f"Package '{package}' is NOT installed")

    def check_configuration(self):
        """Check configuration files"""
        self.print_header("CONFIGURATION CHECKS")

        # Check for config files
        config_files = [
            'config/config.yaml',
            'config/config_comprehensive.yaml'
        ]

        for config_file in config_files:
            if Path(config_file).exists():
                self.print_success(f"Config file exists: {config_file}")

                # Check API key in comprehensive config
                if 'comprehensive' in config_file:
                    with open(config_file, 'r') as f:
                        config = yaml.safe_load(f)
                        api_key = config.get('api', {}).get('youtube_api_key', '')

                        if api_key and api_key != 'YOUR_API_KEY_HERE':
                            self.print_success("API key is configured")
                            self.print_info(f"API key: {api_key[:10]}...{api_key[-4:]}")
                        else:
                            self.print_error("API key is NOT configured properly")

                        # Check quota settings
                        daily_quota = config.get('rate_limiting', {}).get('daily_quota')
                        quota_buffer = config.get('rate_limiting', {}).get('quota_buffer')

                        if daily_quota == 1000000:
                            self.print_success(f"Production quota configured: {daily_quota:,} units")
                        else:
                            self.print_warning(f"Quota set to {daily_quota:,} (expected 1,000,000 for production)")

                        self.print_info(f"Quota buffer: {quota_buffer:,} units")

                        # Check checkpoint settings
                        checkpoint_interval = config.get('collection', {}).get('checkpoint_every_n_channels')
                        self.print_info(f"Checkpoint interval: every {checkpoint_interval} channels")
            else:
                self.print_error(f"Config file NOT found: {config_file}")

    def check_database(self):
        """Check database structure and quota tracking"""
        self.print_header("DATABASE CHECKS")

        db_path = 'data/youtube_monitoring.db'

        if not Path(db_path).exists():
            self.print_warning(f"Database does not exist yet: {db_path}")
            self.print_info("Database will be created on first run")
            return

        self.print_success(f"Database exists: {db_path}")

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Check tables exist
            required_tables = [
                'channels', 'videos', 'comments',
                'collection_runs', 'quota_tracking', 'caption_tracks'
            ]

            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            existing_tables = {row[0] for row in cursor.fetchall()}

            for table in required_tables:
                if table in existing_tables:
                    self.print_success(f"Table '{table}' exists")
                else:
                    self.print_error(f"Table '{table}' is missing")

            # Check for quota_cumulative column
            cursor.execute("PRAGMA table_info(collection_runs)")
            columns = {row[1] for row in cursor.fetchall()}

            if 'quota_cumulative' in columns:
                self.print_success("Column 'quota_cumulative' exists in collection_runs")
            else:
                self.print_error("Column 'quota_cumulative' is MISSING - quota tracking may be broken")

            # Check last collection run
            cursor.execute("""
                SELECT run_id, start_time, status, channels_processed,
                       quota_used, quota_cumulative
                FROM collection_runs
                ORDER BY run_id DESC
                LIMIT 1
            """)

            last_run = cursor.fetchone()
            if last_run:
                self.print_info(f"Last collection run: ID {last_run[0]}")
                self.print_info(f"  Started: {last_run[1]}")
                self.print_info(f"  Status: {last_run[2]}")
                self.print_info(f"  Channels processed: {last_run[3]}")
                self.print_info(f"  Session quota: {last_run[4]:,}" if last_run[4] else "  Session quota: N/A")
                self.print_info(f"  Cumulative quota: {last_run[5]:,}" if last_run[5] else "  Cumulative quota: N/A")
            else:
                self.print_info("No previous collection runs found")

            conn.close()

        except Exception as e:
            self.print_error(f"Database error: {e}")

    def check_directories(self):
        """Check required directories exist"""
        self.print_header("DIRECTORY CHECKS")

        required_dirs = [
            'data',
            'data/checkpoints',
            'data/processed',
            'data/raw',
            'logs',
            'config'
        ]

        for dir_path in required_dirs:
            if Path(dir_path).exists():
                self.print_success(f"Directory exists: {dir_path}")
            else:
                self.print_warning(f"Directory missing: {dir_path} (will be created automatically)")

    def check_source_file(self):
        """Check source CSV file"""
        self.print_header("SOURCE FILE CHECKS")

        source_file = 'data/sources.csv'

        if not Path(source_file).exists():
            self.print_error(f"Source file NOT found: {source_file}")
            return

        self.print_success(f"Source file exists: {source_file}")

        try:
            import pandas as pd
            df = pd.read_csv(source_file)

            # Check required columns
            if 'Youtube' in df.columns:
                self.print_success("Required column 'Youtube' found")
            else:
                self.print_error("Required column 'Youtube' is missing")

            # Count channels
            total_channels = len(df)
            valid_urls = df['Youtube'].notna().sum()

            self.print_info(f"Total rows: {total_channels}")
            self.print_info(f"Valid YouTube URLs: {valid_urls}")

            # Check optional metadata columns
            optional_cols = ['Domain', 'Brand Name', 'Rating', 'Orientation']
            for col in optional_cols:
                if col in df.columns:
                    self.print_info(f"Optional column '{col}' is present")

            # Show sample URLs
            print("\nSample YouTube URLs:")
            for i, url in enumerate(df['Youtube'].dropna().head(3)):
                print(f"  {i+1}. {url}")

        except Exception as e:
            self.print_error(f"Error reading source file: {e}")

    def check_checkpoint(self):
        """Check checkpoint status"""
        self.print_header("CHECKPOINT STATUS")

        checkpoint_file = 'data/checkpoints/latest_checkpoint.json'

        if not Path(checkpoint_file).exists():
            self.print_info("No checkpoint file found (fresh start)")
            return

        self.print_success(f"Checkpoint file exists: {checkpoint_file}")

        try:
            with open(checkpoint_file, 'r') as f:
                checkpoint = json.load(f)

            self.print_info(f"Last checkpoint at channel index: {checkpoint.get('channel_index', 0)}")
            self.print_info(f"Channels processed: {checkpoint.get('channels_processed', 0)}")
            self.print_info(f"Session quota used: {checkpoint.get('quota_usage', 0):,}")
            self.print_info(f"Cumulative quota: {checkpoint.get('quota_cumulative', 0):,}")
            self.print_info(f"Timestamp: {checkpoint.get('timestamp', 'N/A')}")

            self.print_warning("Use --resume flag to continue from this checkpoint")

        except Exception as e:
            self.print_error(f"Error reading checkpoint: {e}")

    def test_api_connection(self):
        """Test API connection"""
        self.print_header("API CONNECTION TEST")

        print("Running test_api_quick.py...")

        try:
            result = subprocess.run(
                ['python', 'test_api_quick.py'],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                self.print_success("API connection test passed")
                print(result.stdout)
            else:
                self.print_error("API connection test failed")
                print(result.stderr)

        except subprocess.TimeoutExpired:
            self.print_error("API test timed out")
        except FileNotFoundError:
            self.print_warning("test_api_quick.py not found - skipping API test")
        except Exception as e:
            self.print_error(f"API test error: {e}")

    def print_summary(self):
        """Print final summary"""
        self.print_header("VERIFICATION SUMMARY")

        total_checks = len(self.checks_passed) + len(self.checks_failed)

        print(f"\n✅ Passed: {len(self.checks_passed)}/{total_checks}")
        print(f"❌ Failed: {len(self.checks_failed)}/{total_checks}")
        print(f"⚠️  Warnings: {len(self.warnings)}")

        if self.checks_failed:
            print("\n⚠️  FAILED CHECKS:")
            for check in self.checks_failed:
                print(f"  - {check}")

        if self.warnings:
            print("\n⚠️  WARNINGS:")
            for warning in self.warnings:
                print(f"  - {warning}")

        if not self.checks_failed:
            print("\n🎉 System is READY for production!")
            print("\nTo start collection:")
            print("  python collect.py --sources data/sources.csv")
            print("\nTo resume from checkpoint:")
            print("  python collect.py --sources data/sources.csv --resume")
        else:
            print("\n❌ System is NOT ready. Please fix the issues above.")

    def run_all_checks(self):
        """Run all verification checks"""
        print("="*60)
        print(" YOUTUBE MONITORING PIPELINE - PRODUCTION VERIFICATION")
        print(" Timestamp:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        print("="*60)

        self.check_environment()
        self.check_configuration()
        self.check_directories()
        self.check_database()
        self.check_source_file()
        self.check_checkpoint()
        self.test_api_connection()
        self.print_summary()

if __name__ == "__main__":
    verifier = ProductionVerifier()
    verifier.run_all_checks()