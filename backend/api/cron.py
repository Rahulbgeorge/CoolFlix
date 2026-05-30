import os
import sys
import fcntl
import logging
from django.db import transaction
from .models import Video
from .transcoder import VideoProcessor

logger = logging.getLogger(__name__)

def run_transcoder_cron():
    """
    Decoupled cron task that processes video tasks in order of priority:
    1. HLS streaming generation for ALL pending videos first.
    2. Sprite sheet generation for videos with completed HLS.
    3. Preview clip/thumbnail generation for videos with completed HLS & sprite.
    """
    # Determine the project root to store the lock file securely
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    lock_file_path = os.path.join(base_dir, 'transcoder.lock')
    
    # Acquire exclusive non-blocking lock to prevent multiple concurrent instances
    lock_file = open(lock_file_path, 'w')
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except IOError:
        logger.info("Another instance of the transcoder is already running. Exiting cron...")
        return

    logger.info("Acquired file lock. Starting prioritized transcoder cycle...")
    
    # 0. Recover stalled jobs on startup
    try:
        Video.objects.filter(status='processing', hls_status='processing').update(hls_status='pending', status='pending', progress=0.0)
        Video.objects.filter(status='processing', sprite_status='processing').update(sprite_status='pending')
        Video.objects.filter(status='processing', preview_status='processing').update(preview_status='pending')
    except Exception as e:
        logger.error(f"Error resetting stalled tasks: {e}")

    # 1. First Priority: Process HLS for all videos where hls_status is 'pending'
    while True:
        video_id = None
        try:
            with transaction.atomic():
                video = Video.objects.filter(
                    status='pending', 
                    hls_status='pending'
                ).order_by('created_at').select_for_update().first()
                
                if video:
                    video.status = 'processing'
                    video.hls_status = 'processing'
                    video.progress = 5.0
                    video.save()
                    video_id = video.id
        except Exception as e:
            logger.error(f"Error fetching pending HLS task: {e}")
            break
            
        if not video_id:
            break
            
        try:
            logger.info(f"Running HLS generation for video ID {video_id}...")
            VideoProcessor.process_hls_only(video_id)
        except Exception as e:
            logger.error(f"Failed HLS generation for video ID {video_id}: {e}")

    # 2. Second Priority: Process sprite sheets for videos where hls_status='completed' and sprite_status='pending'
    while True:
        video_id = None
        try:
            with transaction.atomic():
                video = Video.objects.filter(
                    status='processing', 
                    hls_status='completed', 
                    sprite_status='pending'
                ).order_by('created_at').select_for_update().first()
                
                if video:
                    video.sprite_status = 'processing'
                    video.progress = 80.0
                    video.save()
                    video_id = video.id
        except Exception as e:
            logger.error(f"Error fetching pending sprite task: {e}")
            break
            
        if not video_id:
            break
            
        try:
            logger.info(f"Running Sprite sheet generation for video ID {video_id}...")
            VideoProcessor.process_sprite_only(video_id)
        except Exception as e:
            logger.error(f"Failed Sprite sheet generation for video ID {video_id}: {e}")

    # 3. Third Priority: Process previews for videos where hls_status='completed', sprite_status='completed', preview_status='pending'
    while True:
        video_id = None
        try:
            with transaction.atomic():
                video = Video.objects.filter(
                    status='processing', 
                    hls_status='completed', 
                    sprite_status='completed', 
                    preview_status='pending'
                ).order_by('created_at').select_for_update().first()
                
                if video:
                    video.preview_status = 'processing'
                    video.progress = 90.0
                    video.save()
                    video_id = video.id
        except Exception as e:
            logger.error(f"Error fetching pending preview task: {e}")
            break
            
        if not video_id:
            break
            
        try:
            logger.info(f"Running Preview & Thumbnail generation for video ID {video_id}...")
            VideoProcessor.process_preview_only(video_id)
        except Exception as e:
            logger.error(f"Failed Preview generation for video ID {video_id}: {e}")

    logger.info("Finished prioritized transcoder cycle.")
