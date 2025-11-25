"""
Simple data viewer for inspecting collected YouTube data
"""

import sqlite3
import argparse
from pathlib import Path
from tabulate import tabulate
import sys


def connect_db(db_path: str):
    """Connect to database"""
    if not Path(db_path).exists():
        print(f"Error: Database not found at {db_path}")
        sys.exit(1)
    return sqlite3.connect(db_path)


def view_channels(conn, limit=10):
    """View collected channels"""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT channel_title, subscriber_count, video_count, view_count, 
               source_domain, source_orientation
        FROM channels
        ORDER BY subscriber_count DESC
        LIMIT ?
    """, (limit,))
    
    rows = cursor.fetchall()
    headers = ['Channel', 'Subscribers', 'Videos', 'Views', 'Domain', 'Orientation']
    
    print(f"\n{'='*80}")
    print(f"Top {limit} Channels by Subscribers")
    print(f"{'='*80}")
    print(tabulate(rows, headers=headers, tablefmt='grid'))


def view_videos(conn, channel_title=None, limit=10):
    """View collected videos"""
    cursor = conn.cursor()
    
    if channel_title:
        cursor.execute("""
            SELECT v.title, v.view_count, v.like_count, v.comment_count, 
                   v.published_at, c.channel_title
            FROM videos v
            JOIN channels c ON v.channel_id = c.channel_id
            WHERE c.channel_title LIKE ?
            ORDER BY v.published_at DESC
            LIMIT ?
        """, (f'%{channel_title}%', limit))
    else:
        cursor.execute("""
            SELECT v.title, v.view_count, v.like_count, v.comment_count, 
                   v.published_at, c.channel_title
            FROM videos v
            JOIN channels c ON v.channel_id = c.channel_id
            ORDER BY v.view_count DESC
            LIMIT ?
        """, (limit,))
    
    rows = cursor.fetchall()
    headers = ['Title', 'Views', 'Likes', 'Comments', 'Published', 'Channel']
    
    print(f"\n{'='*80}")
    if channel_title:
        print(f"Videos from channel matching '{channel_title}'")
    else:
        print(f"Top {limit} Videos by Views")
    print(f"{'='*80}")
    
    # Truncate long titles
    formatted_rows = []
    for row in rows:
        title = row[0][:60] + '...' if len(row[0]) > 60 else row[0]
        channel = row[5][:30] + '...' if len(row[5]) > 30 else row[5]
        formatted_rows.append([title, row[1], row[2], row[3], row[4][:10], channel])
    
    print(tabulate(formatted_rows, headers=headers, tablefmt='grid'))


def view_comments(conn, video_title=None, limit=10):
    """View collected comments"""
    cursor = conn.cursor()
    
    if video_title:
        cursor.execute("""
            SELECT co.author_name, co.text, co.like_count, v.title
            FROM comments co
            JOIN videos v ON co.video_id = v.video_id
            WHERE v.title LIKE ?
            ORDER BY co.like_count DESC
            LIMIT ?
        """, (f'%{video_title}%', limit))
    else:
        cursor.execute("""
            SELECT co.author_name, co.text, co.like_count, v.title
            FROM comments co
            JOIN videos v ON co.video_id = v.video_id
            ORDER BY co.like_count DESC
            LIMIT ?
        """, (limit,))
    
    rows = cursor.fetchall()
    headers = ['Author', 'Comment', 'Likes', 'Video']
    
    print(f"\n{'='*80}")
    if video_title:
        print(f"Comments from video matching '{video_title}'")
    else:
        print(f"Top {limit} Comments by Likes")
    print(f"{'='*80}")
    
    # Truncate long text
    formatted_rows = []
    for row in rows:
        author = row[0][:20] + '...' if len(row[0]) > 20 else row[0]
        comment = row[1][:80] + '...' if len(row[1]) > 80 else row[1]
        video = row[3][:40] + '...' if len(row[3]) > 40 else row[3]
        formatted_rows.append([author, comment, row[2], video])
    
    print(tabulate(formatted_rows, headers=headers, tablefmt='grid'))


def show_stats(conn):
    """Show collection statistics"""
    cursor = conn.cursor()
    
    # Get counts
    cursor.execute("SELECT COUNT(*) FROM channels")
    channel_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM videos")
    video_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM comments")
    comment_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(view_count) FROM videos")
    total_views = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT AVG(view_count) FROM videos WHERE view_count > 0")
    avg_views = cursor.fetchone()[0] or 0
    
    cursor.execute("""
        SELECT COUNT(DISTINCT author_channel_id) 
        FROM comments 
        WHERE author_channel_id IS NOT NULL
    """)
    unique_commenters = cursor.fetchone()[0]
    
    # Get recent collection runs
    cursor.execute("""
        SELECT run_id, start_time, end_time, channels_processed, 
               videos_collected, comments_collected, quota_used, status
        FROM collection_runs
        ORDER BY run_id DESC
        LIMIT 5
    """)
    runs = cursor.fetchall()
    
    print(f"\n{'='*80}")
    print("Database Statistics")
    print(f"{'='*80}")
    print(f"Channels:          {channel_count:,}")
    print(f"Videos:            {video_count:,}")
    print(f"Comments:          {comment_count:,}")
    print(f"Total Views:       {total_views:,}")
    print(f"Avg Views/Video:   {avg_views:,.0f}")
    print(f"Unique Commenters: {unique_commenters:,}")
    
    if runs:
        print(f"\n{'='*80}")
        print("Recent Collection Runs")
        print(f"{'='*80}")
        headers = ['Run ID', 'Date', 'Channels', 'Videos', 'Comments', 'Quota', 'Status']
        
        formatted_runs = []
        for run in runs:
            date = run[1][:10] if run[1] else 'Unknown'
            formatted_runs.append([
                run[0], date, run[3], run[4], run[5], run[6], run[7]
            ])
        
        print(tabulate(formatted_runs, headers=headers, tablefmt='grid'))


def main():
    parser = argparse.ArgumentParser(description='View collected YouTube data')
    parser.add_argument('--db', type=str, default='data/youtube_monitoring.db',
                       help='Path to database file')
    parser.add_argument('--stats', action='store_true',
                       help='Show collection statistics')
    parser.add_argument('--channels', type=int, metavar='N',
                       help='Show top N channels')
    parser.add_argument('--videos', type=int, metavar='N',
                       help='Show top N videos')
    parser.add_argument('--comments', type=int, metavar='N',
                       help='Show top N comments')
    parser.add_argument('--channel-name', type=str,
                       help='Filter videos by channel name')
    parser.add_argument('--video-title', type=str,
                       help='Filter comments by video title')
    
    args = parser.parse_args()
    
    # Connect to database
    conn = connect_db(args.db)
    
    try:
        # If no arguments, show stats by default
        if not any([args.stats, args.channels, args.videos, args.comments]):
            show_stats(conn)
        else:
            if args.stats:
                show_stats(conn)
            
            if args.channels:
                view_channels(conn, args.channels)
            
            if args.videos:
                view_videos(conn, args.channel_name, args.videos)
            
            if args.comments:
                view_comments(conn, args.video_title, args.comments)
    
    finally:
        conn.close()


if __name__ == "__main__":
    # Try to import tabulate, suggest install if missing
    try:
        from tabulate import tabulate
    except ImportError:
        print("Error: 'tabulate' package not found")
        print("Install it with: pip install tabulate")
        sys.exit(1)
    
    main()
