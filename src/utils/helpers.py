"""
Utilities for YouTube Monitoring Pipeline
"""

import csv
import logging
import pandas as pd
from typing import List, Dict, Optional
import re

logger = logging.getLogger(__name__)


def load_sources_from_csv(csv_path: str) -> List[Dict]:
    """
    Load YouTube channel sources from CSV file
    
    Args:
        csv_path: Path to CSV file with source data
        
    Returns:
        List of source dictionaries with metadata
    """
    sources = []
    
    try:
        df = pd.read_csv(csv_path, encoding='utf-8')
        
        logger.info(f"Loaded CSV with {len(df)} rows")
        
        for idx, row in df.iterrows():
            youtube_url = row.get('Youtube', '')
            
            # Skip if no YouTube URL
            if pd.isna(youtube_url) or youtube_url.strip() == '':
                continue
            
            # Handle multiple URLs (some rows have comma-separated URLs)
            urls = [url.strip() for url in str(youtube_url).split(',')]
            
            for url in urls:
                if url and url.strip() != '':
                    source = {
                        'youtube_url': url.strip(),
                        'domain': row.get('Domain', ''),
                        'brand_name': row.get('Brand Name', ''),
                        'country': row.get('Country', ''),
                        'language': row.get('Language', ''),
                        'rating': row.get('Rating', ''),
                        'score': row.get('Score', ''),
                        'orientation': row.get('Orientation', ''),
                        'type_of_content': row.get('Type of Content', ''),
                        'topics': row.get('Topics', ''),
                        'owner': row.get('Owner', ''),
                        'type_of_owner': row.get('Type of Owner', ''),
                    }
                    sources.append(source)
        
        logger.info(f"Extracted {len(sources)} YouTube channels from CSV")
        return sources
        
    except Exception as e:
        logger.error(f"Error loading sources from CSV: {e}")
        return []


def extract_channel_id_from_url(url: str) -> Optional[str]:
    """
    Extract channel ID or handle from YouTube URL
    
    Args:
        url: YouTube channel URL
        
    Returns:
        Channel ID, handle, or username
    """
    if not url or url.strip() == "":
        return None
    
    url = url.strip()
    
    # Remove query parameters
    url = url.split('?')[0]
    
    # Handle youtube.com/channel/ID format
    if '/channel/' in url:
        return url.split('/channel/')[-1].split('/')[0]
    
    # Handle youtube.com/@handle format
    if '/@' in url:
        return '@' + url.split('/@')[-1].split('/')[0]
    
    # Handle youtube.com/c/NAME format
    if '/c/' in url:
        return url.split('/c/')[-1].split('/')[0]
    
    # Handle youtube.com/user/NAME format
    if '/user/' in url:
        return url.split('/user/')[-1].split('/')[0]
    
    # Handle direct channel name
    if 'youtube.com/' in url:
        parts = url.split('youtube.com/')[-1].split('/')
        if parts and parts[0]:
            return parts[0]
    
    logger.warning(f"Could not extract channel ID from URL: {url}")
    return None


def format_duration(seconds: int) -> str:
    """
    Format duration in seconds to human-readable string
    
    Args:
        seconds: Duration in seconds
        
    Returns:
        Formatted duration string (e.g., "2:34:15")
    """
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes}:{secs:02d}"


def clean_text(text: str) -> str:
    """
    Clean text for analysis (remove extra whitespace, etc.)
    
    Args:
        text: Input text
        
    Returns:
        Cleaned text
    """
    if not text:
        return ""
    
    # Remove multiple spaces
    text = re.sub(r'\s+', ' ', text)
    
    # Strip leading/trailing whitespace
    text = text.strip()
    
    return text


def calculate_engagement_rate(video_data: Dict) -> float:
    """
    Calculate engagement rate for a video
    
    Args:
        video_data: Dictionary with video statistics
        
    Returns:
        Engagement rate (0-1)
    """
    try:
        views = int(video_data.get('view_count', 0))
        likes = int(video_data.get('like_count', 0))
        comments = int(video_data.get('comment_count', 0))
        
        if views == 0:
            return 0.0
        
        engagement = (likes + comments) / views
        return engagement
        
    except Exception as e:
        logger.error(f"Error calculating engagement rate: {e}")
        return 0.0


def categorize_video_length(duration_seconds: int) -> str:
    """
    Categorize video by length
    
    Args:
        duration_seconds: Video duration in seconds
        
    Returns:
        Category string
    """
    if duration_seconds < 60:
        return 'very_short'  # < 1 min
    elif duration_seconds < 300:
        return 'short'  # 1-5 min
    elif duration_seconds < 1200:
        return 'medium'  # 5-20 min
    elif duration_seconds < 3600:
        return 'long'  # 20-60 min
    else:
        return 'very_long'  # > 1 hour


def setup_logging(log_level: str = 'INFO', log_file: Optional[str] = None):
    """
    Setup logging configuration
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional path to log file
    """
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Setup root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # File handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    
    logger.info(f"Logging initialized at {log_level} level")


def save_json(data: Dict, output_path: str) -> bool:
    """
    Save data as JSON file
    
    Args:
        data: Data to save
        output_path: Path for output file
        
    Returns:
        True if successful, False otherwise
    """
    try:
        import json
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved JSON to {output_path}")
        return True
        
    except Exception as e:
        logger.error(f"Error saving JSON: {e}")
        return False


def load_json(input_path: str) -> Optional[Dict]:
    """
    Load data from JSON file
    
    Args:
        input_path: Path to JSON file
        
    Returns:
        Loaded data or None if error
    """
    try:
        import json
        
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        logger.info(f"Loaded JSON from {input_path}")
        return data
        
    except Exception as e:
        logger.error(f"Error loading JSON: {e}")
        return None