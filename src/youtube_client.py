"""
YouTube API Client Wrapper
Handles all interactions with the YouTube Data API v3
"""

import json
import logging
import random
import time
from typing import List, Dict, Optional, Any
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import isodate

from src.errors import (
    QuotaExhausted, CommentsDisabled, ItemUnavailable, APIError,
    QUOTA_REASONS, RATE_LIMIT_REASONS, UNAVAILABLE_REASONS,
    COMMENTS_DISABLED_REASONS, RETRYABLE_STATUSES,
)
from src.quota import COSTS

logger = logging.getLogger(__name__)

# api_method labels (kept for the quota_tracking table and existing callers)
# mapped to the endpoint names the governor prices and bills.
_METHOD_ENDPOINTS = {
    'channels.list': 'channels',
    'channels.list_forUsername': 'channels',
    'channels.list_forHandle': 'channels',
    'playlistItems.list': 'playlistItems',
    'videos.list': 'videos',
    'commentThreads.list': 'commentThreads',
    'comments.list': 'comments',
    'captions.list': 'captions',
    'search.list': 'search',
}


def _error_detail(error: HttpError) -> tuple:
    """Extract (reason, message) from an HttpError body."""
    try:
        payload = json.loads(error.content.decode('utf-8'))
        err = payload.get('error', {})
        errors = err.get('errors') or [{}]
        return errors[0].get('reason', ''), str(err.get('message', ''))[:300]
    except Exception:
        try:
            return '', error.content.decode('utf-8', 'replace')[:300]
        except Exception:
            return '', str(error)[:300]


class YouTubeAPIClient:
    """Wrapper for YouTube Data API v3"""
    
    def __init__(self, api_key: str, max_retries: int = 3, retry_delay: int = 2,
                 initial_quota: int = 0, db=None, run_id: int = None,
                 governor=None, allow_search: bool = False):
        """
        Initialize YouTube API client

        Args:
            api_key: YouTube Data API key
            max_retries: Maximum number of retries for failed requests
            retry_delay: Delay between retries in seconds
            initial_quota: Starting quota value (for resuming)
            db: Database instance for quota tracking
            run_id: Collection run ID for quota tracking
            governor: QuotaGovernor enforcing the daily budget. Without one the
                client still counts units but cannot refuse a call.
            allow_search: Permit the 100-unit search.list URL-resolution
                fallback. Off by default: only backfill/resolution entry points
                turn it on. Independent of the governor's own endpoint ban, so
                the daily path is guarded twice.
        """
        self.api_key = api_key
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.youtube = build('youtube', 'v3', developerKey=api_key)
        self.quota_usage = 0  # Session quota
        self.quota_cumulative = initial_quota  # Cumulative quota
        self.db = db
        self.run_id = run_id
        self.governor = governor
        self.allow_search = allow_search

        logger.info(f"YouTube API client initialized with cumulative quota: {initial_quota}")

    def _call(self, request_func, endpoint: str = None, quota_cost: int = None,
              api_method: str = None) -> Any:
        """
        The single chokepoint every API call goes through.

        Contract:
          1. refuse before calling if the governor cannot afford the endpoint;
          2. charge the ledger only on a served response;
          3. raise QuotaExhausted on 403 quotaExceeded/dailyLimitExceeded;
          4. retry with backoff on rate-limit reasons and 5xx;
          5. raise ItemUnavailable on channel/video/playlistNotFound.

        Never returns None to mean "failed" -- the distinction between "spent"
        and "absent" is what the exception types carry.

        Args:
            request_func: Callable executing the API request
            endpoint: Endpoint name for pricing/billing (derived from
                api_method when omitted)
            quota_cost: Override the published cost (tests and odd parts)
            api_method: Label recorded in quota_tracking

        Returns:
            Parsed API response
        """
        if endpoint is None:
            endpoint = _METHOD_ENDPOINTS.get(api_method or '', api_method or 'channels')
        if quota_cost is None:
            quota_cost = COSTS.get(endpoint, 1)

        # Guard 1: the caller-level flag. search.list is reachable from the
        # URL-resolution fallback, which the daily path must never trigger.
        if endpoint == 'search' and not self.allow_search:
            raise QuotaExhausted(
                "search.list (100 units) refused: allow_search is False. "
                "Discovery goes through playlistItems on channels.uploads_playlist."
            )

        # Guard 2: the governor's own endpoint ban, independent of the flag.
        if self.governor is not None and self.governor.is_forbidden(endpoint):
            raise QuotaExhausted(f"endpoint {endpoint!r} is not permitted on this path")

        if self.governor is not None and not self.governor.can_afford(quota_cost):
            raise QuotaExhausted(
                f"budget spent: {self.governor.spent_today()}/"
                f"{self.governor.daily_budget} units today; "
                f"{endpoint} needs {quota_cost}"
            )

        for attempt in range(self.max_retries):
            try:
                response = request_func()
            except HttpError as e:
                status = e.resp.status
                reason, message = _error_detail(e)

                if status == 403 and reason in QUOTA_REASONS:
                    # The 403-swallow bug lived here: this used to be returned
                    # as None and recorded as "channel not found". It must
                    # reach the caller so the run stops with nothing written.
                    logger.error(f"Quota exhausted on {endpoint}: {reason}: {message}")
                    raise QuotaExhausted(f"{reason}: {message}")

                if (status in (403, 429)) and reason in RATE_LIMIT_REASONS:
                    if attempt < self.max_retries - 1:
                        delay = 5 * (attempt + 1) + random.random()
                        logger.warning(f"Rate limited on {endpoint}, retrying in {delay:.1f}s")
                        time.sleep(delay)
                        continue
                    raise QuotaExhausted(f"{reason}: {message}")

                # From here down the API *served* the request and billed for
                # it, even though it answered with an error. Charging only on
                # HTTP 200 made the ledger under-count: on 2026-09-16 the
                # first live run left 212 commentsDisabled responses uncharged
                # and the ledger read 4.25% below the Cloud console. Worse than
                # the reporting gap, the governor then believed it had 212 more
                # units than it did, so it could overspend the real ceiling.
                # Quota exhaustion and rate limiting are excluded above: those
                # are refusals, not served requests.
                if reason in COMMENTS_DISABLED_REASONS:
                    self._charge_error(endpoint, quota_cost, api_method)
                    raise CommentsDisabled(message)

                if status in (403, 404) and reason in UNAVAILABLE_REASONS:
                    self._charge_error(endpoint, quota_cost, api_method)
                    raise ItemUnavailable(f"{reason}: {message}")

                if status in RETRYABLE_STATUSES and attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2 ** attempt) + random.random()
                    logger.warning(f"{status} on {endpoint}, retrying in {delay:.1f}s")
                    time.sleep(delay)
                    continue

                # A 5xx that exhausted its retries was still served each time,
                # but the API does not bill failed server-side attempts; a 4xx
                # that reaches here was served and billed.
                if status < 500:
                    self._charge_error(endpoint, quota_cost, api_method)
                raise APIError(status, reason, message)

            except (QuotaExhausted, CommentsDisabled, ItemUnavailable, APIError):
                raise
            except Exception as e:
                if attempt < self.max_retries - 1:
                    logger.warning(
                        f"Transport error on {endpoint} "
                        f"(attempt {attempt + 1}/{self.max_retries}): {e}"
                    )
                    time.sleep(self.retry_delay * (attempt + 1))
                    continue
                logger.error(f"Request failed after {self.max_retries} attempts: {e}")
                raise

            # Served with a 200: charge it.
            self._charge(endpoint, quota_cost, api_method)

            logger.debug(
                f"{endpoint} served. Session quota: {self.quota_usage}, "
                f"Cumulative: {self.quota_cumulative}"
            )
            return response

        raise APIError(0, 'retries_exhausted', endpoint)

    def _charge(self, endpoint: str, quota_cost: int, api_method: str = None) -> None:
        """Record units for a response the API served with HTTP 200."""
        if self.governor is not None:
            self.governor.charge(endpoint, quota_cost)
        self.quota_usage += quota_cost
        self.quota_cumulative += quota_cost
        if self.db and self.run_id and api_method:
            self.db.track_quota_usage(self.run_id, api_method, quota_cost)

    def _charge_error(self, endpoint: str, quota_cost: int,
                      api_method: str = None) -> None:
        """
        Record a response the API served with a non-quota error.

        Always counted in quota_ledger.error_calls; charged units only when
        quota.charge_error_responses is set on the governor. Whether YouTube
        bills these is undocumented, and 2026-09-16 could not settle it -- the
        console read below the ledger that day. Counting them separately makes
        the question answerable from any later day without putting the
        governor's budget arithmetic at risk in the meantime.

        Refusals are never counted here: a quotaExceeded or rate-limit response
        is the API declining to serve, not serving an error.
        """
        if self.governor is None:
            return
        self.governor.charge_error(endpoint, quota_cost)
        if self.governor.charge_error_responses:
            self.quota_usage += quota_cost
            self.quota_cumulative += quota_cost
            if self.db and self.run_id and api_method:
                self.db.track_quota_usage(self.run_id, api_method, quota_cost)

    def _make_request(self, request_func, quota_cost: int = 1, api_method: str = None) -> Any:
        """
        Backwards-compatible alias for _call, kept for existing callers
        (collect.py, scripts/revalidate_contaminated.py).
        """
        return self._call(request_func, quota_cost=quota_cost, api_method=api_method)


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
            
            # Search as last resort, at 100 units. Gated by allow_search, which
            # _call enforces: on the daily path this raises rather than spends.
            if not self.allow_search:
                logger.info(
                    f"No cheap resolution for {username!r} and search.list is "
                    f"disabled on this path; treating as unresolved."
                )
                return None

            request = self.youtube.search().list(
                part='snippet',
                q=username,
                type='channel',
                maxResults=1
            )
            response = self._call(lambda: request.execute(), endpoint='search',
                                  api_method='search.list')

            if response and response.get('items'):
                channel_id = response['items'][0]['id']['channelId']
                return self.get_channel_info(channel_id)

            logger.warning(f"Could not find channel for username: {username}")
            return None

        except (QuotaExhausted, ItemUnavailable, APIError):
            # Deliberately not swallowed. A quota failure is not a missing
            # channel, and callers must be able to tell the two apart.
            raise
        except Exception as e:
            logger.error(f"Unexpected error getting channel by username {username}: {e}")
            raise
    
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
                part='snippet,statistics,contentDetails,brandingSettings,topicDetails,status',
                id=channel_id
            )
            response = self._call(lambda: request.execute(), endpoint='channels',
                                  api_method='channels.list')

            if response and response.get('items'):
                return response['items'][0]

            # An empty items list is the only honest "not found": the call was
            # served, cost a unit, and came back with nothing.
            logger.warning(f"No channel found for ID: {channel_id}")
            return None

        except (QuotaExhausted, ItemUnavailable, APIError):
            # Was: blanket `except Exception -> return None`, which turned a
            # quotaExceeded 403 into a recorded not-found. That contaminated
            # ~752 entries across Runs #2 and #3d (see LOGBOOK, Known bugs).
            raise
        except Exception as e:
            logger.error(f"Unexpected error getting channel info for {channel_id}: {e}")
            raise
    
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

        except QuotaExhausted:
            # Returning the partial list here would let the caller record the
            # channel as fully collected when it is only partly collected.
            raise
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

        except QuotaExhausted:
            raise
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
                        
                except CommentsDisabled:
                    # Previously any 403 was read as "comments disabled",
                    # quotaExceeded included. _call now separates the two, so
                    # only a genuine commentsDisabled reason lands here.
                    logger.warning(f"Comments disabled for video {video_id}")
                    break
                except ItemUnavailable as e:
                    logger.warning(f"Video {video_id} unavailable: {e}")
                    break

            logger.info(f"Retrieved {len(comments)} comments for video {video_id}")
            return comments

        except QuotaExhausted:
            raise
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
            
        except QuotaExhausted:
            raise
        except (ItemUnavailable, APIError) as e:
            # captions.list is forbidden without OAuth for most channels; that
            # is expected and not worth failing the video over.
            logger.warning(f"Cannot access captions for video {video_id}: {e}")
            return []
        except HttpError as e:
            logger.error(f"Error getting captions for video {video_id}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error getting captions for video {video_id}: {e}")
            return []
    
    # ---- batch endpoints used by the daily pipeline ----------------------
    # One call per endpoint, no partial-result swallowing: these raise the
    # taxonomy so the stage can decide whether to stop or skip an item.

    def channels_by_id(self, ids: List[str],
                       part: str = 'snippet,statistics,contentDetails,topicDetails,status') -> Dict:
        """channels.list for up to 50 ids. 1 unit for the whole batch."""
        if len(ids) > 50:
            raise ValueError("channels.list accepts at most 50 ids per call")
        request = self.youtube.channels().list(part=part, id=','.join(ids), maxResults=50)
        return self._call(lambda: request.execute(), endpoint='channels',
                          api_method='channels.list')

    def videos_by_id(self, ids: List[str],
                     part: str = 'snippet,statistics,contentDetails,topicDetails,status') -> Dict:
        """videos.list for up to 50 ids. 1 unit for the whole batch."""
        if len(ids) > 50:
            raise ValueError("videos.list accepts at most 50 ids per call")
        request = self.youtube.videos().list(part=part, id=','.join(ids), maxResults=50)
        return self._call(lambda: request.execute(), endpoint='videos',
                          api_method='videos.list')

    def playlist_items(self, playlist_id: str, page_token: str = None) -> Dict:
        """One page of a playlist, 50 items, 1 unit. The discovery path."""
        request = self.youtube.playlistItems().list(
            part='contentDetails,status', playlistId=playlist_id,
            maxResults=50, pageToken=page_token)
        return self._call(lambda: request.execute(), endpoint='playlistItems',
                          api_method='playlistItems.list')

    def comment_threads(self, video_id: str, page_token: str = None,
                        order: str = 'time') -> Dict:
        """One page of comment threads, 100 items, 1 unit."""
        request = self.youtube.commentThreads().list(
            part='snippet,replies', videoId=video_id, maxResults=100,
            order=order, textFormat='plainText', pageToken=page_token)
        return self._call(lambda: request.execute(), endpoint='commentThreads',
                          api_method='commentThreads.list')

    def comment_replies(self, parent_id: str, page_token: str = None) -> Dict:
        """One page of replies to a comment, 100 items, 1 unit."""
        request = self.youtube.comments().list(
            part='snippet', parentId=parent_id, maxResults=100,
            textFormat='plainText', pageToken=page_token)
        return self._call(lambda: request.execute(), endpoint='comments',
                          api_method='comments.list')

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