"""
YouTube Data Collector
Main orchestrator for collecting channel, video, and comment data
"""

import sys
import logging
import yaml
import time
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
import json

# Add parent directory to path so imports work
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.youtube_client import YouTubeAPIClient
from src.database import Database
from src.utils.helpers import (
    load_sources_from_csv,
    extract_channel_id_from_url,
    setup_logging,
    save_json
)

logger = logging.getLogger(__name__)
