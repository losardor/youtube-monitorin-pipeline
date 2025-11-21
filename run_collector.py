#!/usr/bin/env python3
"""
Wrapper script to run the collector with correct imports
"""
import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

# Now import and run
from src.collector import YouTubeCollector
import argparse

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='YouTube Data Collector')
    parser.add_argument('--sources', type=str, required=True,
                       help='Path to CSV file with source data')
    parser.add_argument('--max-channels', type=int, default=None,
                       help='Maximum number of channels to process (for testing)')
    parser.add_argument('--config', type=str, default='config/config.yaml',
                       help='Path to configuration file')
    
    args = parser.parse_args()
    
    # Run collector
    collector = YouTubeCollector(config_path=args.config)
    try:
        collector.run_collection(args.sources, max_channels=args.max_channels)
    finally:
        collector.close()
