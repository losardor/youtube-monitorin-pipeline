"""
YouTube API Client Wrapper
Handles all interactions with the YouTube Data API v3
"""

import time
import logging
from typing import List, Dict, Optional, Any
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import isodate

logger = logging.getLogger(__name__)


class YouTubeAPIClient:
    """Wrapper for YouTube Data API v3"""
    
    def __init__(self, api_key: str, max_retries: int = 3, retry_delay: int = 2,
                 initial_quota: int = 0, db=None, run_id: int = None):
        """
        Initialize YouTube API client

        Args:
            api_key: YouTube Data API key
            max_retries: Maximum number of retries for failed requests
            retry_delay: Delay between retries in seconds
            initial_quota: Starting quota value (for resuming)
            db: Database instance for quota tracking
            run_id: Collection run ID for quota tracking
        """
        self.api_key = api_key
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.youtube = build('youtube', 'v3', developerKey=api_key)
        self.quota_usage = 0  # Session quota
        self.quota_cumulative = initial_quota  # Cumulative quota
        self.db = db
        self.run_id = run_id

        logger.info(f"YouTube API client initialized with cumulative quota: {initial_quota}")
    
    def _make_request(self, request_func, quota_cost: int = 1, api_method: str = None) -> Any:
        """
        Make API request with retry logic

        Args:
            request_func: Function that executes the API request
            quota_cost: Estimated quota cost of this request
            api_method: Name of API method for tracking

        Returns:
            API response
        """
        for attempt in range(self.max_retries):
            try:
                response = request_func()
                self.quota_usage += quota_cost
                self.quota_cumulative += quota_cost

                # Track quota in database if available
                if self.db and self.run_id and api_method:
                    self.db.track_quota_usage(self.run_id, api_method, quota_cost)

                logger.debug(f"API request successful. Session quota: {self.quota_usage}, Cumulative: {self.quota_cumulative}")
                return response
            except HttpError as e:
                if e.resp.status in [403, 429]:  # Quota exceeded or rate limit
                    logger.error(f"Quota/rate limit error: {e}")
                    raise
                elif attempt < self.max_retries - 1:
                    logger.warning(f"Request failed (attempt {attempt + 1}/{self.max_retries}): {e}")
                    time.sleep(self.retry_delay * (attempt + 1))
                else:
                    logger.error(f"Request failed after {self.max_retries} attempts: {e}")
                    raise
            except Exception as e:
                logger.error(f"Unexpected error in API request: {e}")
                raise
        
        return None
    
    def extract_channel_id(self, url: str) -> Optional[str]:
        """
        Extract channel ID from various YouTube URL formats
        
        Args:
            url: YouTube channel URL
            
        Returns:
            Channel ID or handle
        """
        if not url or url.strip() == "":
            return None
        
        url = url.strip()
        
        # Handle youtube.com/channel/ID format
        if '/channel/' in url:
            return url.split('/channel/')[-1].split('/')[0].split('?')[0]
        
        # Handle youtube.com/c/NAME or youtube.com/@handle format
        if '/c/' in url or '/@' in url:
            # Return the custom name/handle - we'll need to resolve it
            if '/c/' in url:
                return url.split('/c/')[-1].split('/')[0].split('?')[0]
            else:
                return '@' + url.split('/@')[-1].split('/')[0].split('?')[0]
        
        # Handle youtube.com/user/NAME format
        if '/user/' in url:
            return url.split('/user/')[-1].split('/')[0].split('?')[0]
        
        logger.warning(f"Could not extract channel ID from URL: {url}")
        return None
    
    def get_channel_by_username(self, username: str) -> Optional[Dict]:
        """
        Get channel information by username or custom URL
        
        Args:
            username: Channel username or handle
            
        Returns:
            Channel information
        """
        try:
            # Try forUsername first
            request = self.youtube.channels().list(
                part='snippet,statistics,contentDetails',
                forUsername=username
            )
            response = self._make_request(lambda: request.execute(), quota_cost=1, api_method='channels.list_forUsername')
            
            if response and response.get('items'):
                return response['items'][0]
            
            # Try forHandle if username starts with @
            if username.startswith('@'):
                request = self.youtube.channels().list(
                    part='snippet,statistics,contentDetails',
                    forHandle=username
                )
                response = self._make_request(lambda: request.execute(), quota_cost=1, api_method='channels.list_forHandle')
                
                if response and response.get('items'):
                    return response['items'][0]
            
            # Try search as last resort
            request = self.youtube.search().list(
                part='snippet',
                q=username,
                type='channel',
                maxResults=1
            )
            response = self._make_request(lambda: request.execute(), quota_cost=100, api_method='search.list')
            
            if response and response.get('items'):
                channel_id = response['items'][0]['id']['channelId']
                return self.get_channel_info(channel_id)
            
            logger.warning(f"Could not find channel for username: {username}")
            return None
            
        except Exception as e:
            logger.error(f"Error getting channel by username {username}: {e}")
            return None
    
    def get_channel_info(self, channel_id: str) -> Optional[Dict]:
        """
        Get channel information
        
        Args:
            channel_id: YouTube channel ID
            
        Returns:
            Channel information dictionary
        """
        try:
            # If channel_id looks like a custom URL or username, resolve it first
            if not channel_id.startswith('UC') or len(channel_id) != 24:
                return self.get_channel_by_username(channel_id)
            
            request = self.youtube.channels().list(
                part='snippet,statistics,contentDetails,brandingSettings',
                id=channel_id
            )
            response = self._make_request(lambda: request.execute(), quota_cost=1, api_method='channels.list')
            
            if response and response.get('items'):
                return response['items'][0]
            
            logger.warning(f"No channel found for ID: {channel_id}")
            return None
            
        except Exception as e:
            logger.error(f"Error getting channel info for {channel_id}: {e}")
            return None
    
    def get_channel_videos(self, channel_id: str, max_results: int = 50, 
                          order: str = 'date', published_after: str = None,
                          published_before: str = None) -> List[Dict]:
        """
        Get videos from a channel
        
        Args:
            channel_id: YouTube channel ID
            max_results: Maximum number of videos to retrieve
            order: Sort order (date, rating, relevance, title, videoCount, viewCount)
            published_after: RFC 3339 formatted date-time value (e.g., 2024-01-01T00:00:00Z)
            published_before: RFC 3339 formatted date-time value
            
        Returns:
            List of video dictionaries
        """
        videos = []
        
        try:
            # Get uploads playlist ID
            channel_info = self.get_channel_info(channel_id)
            if not channel_info:
                return videos
            
            uploads_playlist_id = channel_info['contentDetails']['relatedPlaylists']['uploads']
            
            next_page_token = None
            
            while len(videos) < max_results:
                request_params = {
                    'part': 'snippet,contentDetails',
                    'playlistId': uploads_playlist_id,
                    'maxResults': min(50, max_results - len(videos))
                }
                
                if next_page_token:
                    request_params['pageToken'] = next_page_token
                
                request = self.youtube.playlistItems().list(**request_params)
                response = self._make_request(lambda: request.execute(), quota_cost=1, api_method='playlistItems.list')
                
                if not response:
                    break
                
                for item in response.get('items', []):
                    video_id = item['contentDetails']['videoId']
                    
                    # Check date filters
                    published_at = item['snippet']['publishedAt']
                    if published_after and published_at < published_after:
                        continue
                    if published_before and published_at > published_before:
                        continue
                    
                    videos.append({
                        'video_id': video_id,
                        'title': item['snippet']['title'],
                        'description': item['snippet']['description'],
                        'published_at': published_at,
                        'channel_id': channel_id,
                        'channel_title': item['snippet']['channelTitle']
                    })
                
                next_page_token = response.get('nextPageToken')
                if not next_page_token:
                    break
            
            logger.info(f"Retrieved {len(videos)} videos from channel {channel_id}")
            return videos
            
        except Exception as e:
            logger.error(f"Error getting videos for channel {channel_id}: {e}")
            return videos
    
    def get_video_details(self, video_ids: List[str]) -> List[Dict]:
        """
        Get detailed information for videos (batch request)
        
        Args:
            video_ids: List of video IDs (up to 50 per request)
            
        Returns:
            List of detailed video dictionaries
        """
        all_videos = []
        
        try:
            # Process in batches of 50
            for i in range(0, len(video_ids), 50):
                batch = video_ids[i:i+50]
                
                request = self.youtube.videos().list(
                    part='snippet,statistics,contentDetails,topicDetails,status',
                    id=','.join(batch)
                )
                response = self._make_request(lambda: request.execute(), quota_cost=1, api_method='videos.list')
                
                if response:
                    all_videos.extend(response.get('items', []))
            
            logger.info(f"Retrieved details for {len(all_videos)} videos")
            return all_videos
            
        except Exception as e:
            logger.error(f"Error getting video details: {e}")
            return all_videos
    
    def get_video_comments(self, video_id: str, max_results: int = 100,
                          order: str = 'time') -> List[Dict]:
        """
        Get comments for a video
        
        Args:
            video_id: YouTube video ID
            max_results: Maximum number of comments to retrieve
            order: Sort order (time or relevance)
            
        Returns:
            List of comment dictionaries (includes replies)
        """
        comments = []
        
        try:
            next_page_token = None
            
            while len(comments) < max_results:
                request_params = {
                    'part': 'snippet,replies',
                    'videoId': video_id,
                    'maxResults': min(100, max_results - len(comments)),
                    'order': order,
                    'textFormat': 'plainText'
                }
                
                if next_page_token:
                    request_params['pageToken'] = next_page_token
                
                try:
                    request = self.youtube.commentThreads().list(**request_params)
                    response = self._make_request(lambda: request.execute(), quota_cost=1, api_method='commentThreads.list')
                    
                    if not response:
                        break
                    
                    for item in response.get('items', []):
                        # Top-level comment
                        top_comment = item['snippet']['topLevelComment']['snippet']
                        comment_data = {
                            'comment_id': item['snippet']['topLevelComment']['id'],
                            'video_id': video_id,
                            'text': top_comment['textDisplay'],
                            'author': top_comment['authorDisplayName'],
                            'author_channel_id': top_comment.get('authorChannelId', {}).get('value'),
                            'like_count': top_comment['likeCount'],
                            'published_at': top_comment['publishedAt'],
                            'updated_at': top_comment['updatedAt'],
                            'parent_id': None,
                            'reply_count': item['snippet']['totalReplyCount']
                        }
                        comments.append(comment_data)
                        
                        # Add replies if present
                        if 'replies' in item:
                            for reply in item['replies']['comments']:
                                reply_snippet = reply['snippet']
                                reply_data = {
                                    'comment_id': reply['id'],
                                    'video_id': video_id,
                                    'text': reply_snippet['textDisplay'],
                                    'author': reply_snippet['authorDisplayName'],
                                    'author_channel_id': reply_snippet.get('authorChannelId', {}).get('value'),
                                    'like_count': reply_snippet['likeCount'],
                                    'published_at': reply_snippet['publishedAt'],
                                    'updated_at': reply_snippet['updatedAt'],
                                    'parent_id': comment_data['comment_id'],
                                    'reply_count': 0
                                }
                                comments.append(reply_data)
                    
                    next_page_token = response.get('nextPageToken')
                    if not next_page_token:
                        break
                        
                except HttpError as e:
                    if e.resp.status == 403:
                        # Comments disabled for this video
                        logger.warning(f"Comments disabled for video {video_id}")
                        break
                    else:
                        raise
            
            logger.info(f"Retrieved {len(comments)} comments for video {video_id}")
            return comments
            
        except Exception as e:
            logger.error(f"Error getting comments for video {video_id}: {e}")
            return comments
    
    def get_video_captions(self, video_id: str) -> List[Dict]:
        """
        Get available captions for a video
        
        Note: This only lists available captions. Downloading caption content
        requires OAuth2 authentication and is not available with API key alone.
        
        Args:
            video_id: YouTube video ID
            
        Returns:
            List of available caption tracks
        """
        try:
            request = self.youtube.captions().list(
                part='snippet',
                videoId=video_id
            )
            response = self._make_request(lambda: request.execute(), quota_cost=50, api_method='captions.list')
            
            if response:
                captions = response.get('items', [])
                logger.info(f"Found {len(captions)} caption tracks for video {video_id}")
                return captions
            
            return []
            
        except HttpError as e:
            if e.resp.status == 403:
                logger.warning(f"Cannot access captions for video {video_id} (requires OAuth)")
            else:
                logger.error(f"Error getting captions for video {video_id}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error getting captions for video {video_id}: {e}")
            return []
    
    def get_quota_usage(self) -> int:
        """Get current session quota usage"""
        return self.quota_usage

    def get_quota_cumulative(self) -> int:
        """Get cumulative quota usage across all sessions"""
        return self.quota_cumulative

    def reset_quota_counter(self):
        """Reset quota usage counter (call at start of new day)"""
        self.quota_usage = 0
        self.quota_cumulative = 0
        logger.info("Quota counter reset")