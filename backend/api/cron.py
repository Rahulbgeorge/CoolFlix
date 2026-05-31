import os
import sys
import fcntl
import logging
from django.db import transaction
from .models import Video
from .transcoder import VideoProcessor

logger = logging.getLogger(__name__)

def run_preview_clip_thumbnail_cron():
    """
    
    Decoupled cron task that processes video tasks in order of priority:
    1. Quick database preview clip & thumbnail generation (Priority 1, runs instantly).
    """
    # Determine the project root to store the lock file securely
    Video.objects.filter(preview_clip_status='processing').update(preview_clip_status='pending')
    Video.objects.filter(preview_status='processing').update(preview_status='pending')
    

def run_transcoder_cron():
    """
    Decoupled cron task that processes video tasks in order of priority:
    1. Quick database preview clip & thumbnail generation (Priority 1, runs instantly).
    2. Sprite sheet generation for pending videos (Priority 2, once preview clip is completed).
    3. Physical preview clip generation (Priority 3, if pending/requested).
    4. HLS streaming generation on the backburner (Priority 4, once sprite and preview are done/skipped).
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
        Video.objects.filter(hls_status='processing').update(hls_status='pending')
        Video.objects.filter(sprite_status='processing').update(sprite_status='pending')
        Video.objects.filter(status='processing').update(status='pending')
    except Exception as e:
        logger.error(f"Error resetting stalled tasks: {e}")

    # 1. First Priority: Process quick preview clips for any video where preview_clip_status is 'pending'
    while True:
        video_id = None
        try:
            with transaction.atomic():
                video = Video.objects.filter(
                    preview_clip_status='pending'
                ).exclude(status='failed').order_by('created_at').select_for_update().first()
                
                if video:
                    video.status = 'processing'
                    video.preview_clip_status = 'processing'
                    video.progress = 2.0
                    video.save()
                    video_id = video.id
        except Exception as e:
            logger.error(f"Error fetching pending preview clip task: {e}")
            break
            
        if not video_id:
            break
            
        try:
            logger.info(f"Running Preview clip & thumbnail generation for video ID {video_id}...")
            VideoProcessor.process_preview_clip_only(video_id)
        except Exception as e:
            logger.error(f"Failed Preview clip generation for video ID {video_id}: {e}")

    # 2. Second Priority: Process sprite sheets for any video where sprite_status is 'pending' and preview clip is completed
    while True:
        video_id = None
        try:
            with transaction.atomic():
                video = Video.objects.filter(
                    sprite_status='pending',
                    preview_clip_status='completed'
                ).exclude(status='failed').order_by('created_at').select_for_update().first()
                
                if video:
                    video.status = 'processing'
                    video.sprite_status = 'processing'
                    video.progress = 5.0
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

    # 3. Third Priority: Process physical previews for videos where sprite_status='completed' and preview_status='pending'
    while True:
        video_id = None
        try:
            with transaction.atomic():
                video = Video.objects.filter(
                    sprite_status='completed',
                    preview_status='pending'
                ).exclude(status='failed').order_by('created_at').select_for_update().first()
                
                if video:
                    video.status = 'processing'
                    video.preview_status = 'processing'
                    video.progress = 35.0
                    video.save()
                    video_id = video.id
        except Exception as e:
            logger.error(f"Error fetching pending physical preview task: {e}")
            break
            
        if not video_id:
            break
            
        try:
            logger.info(f"Running Physical Preview generation for video ID {video_id}...")
            VideoProcessor.process_preview_only(video_id)
        except Exception as e:
            logger.error(f"Failed Physical Preview generation for video ID {video_id}: {e}")

    # 4. Fourth Priority: Process HLS transcoding for videos where sprite/preview are done and hls is pending
    while True:
        video_id = None
        try:
            with transaction.atomic():
                video = Video.objects.filter(
                    hls_status='pending',
                    hls_required=True,
                    sprite_status='completed',
                    preview_status__in=['completed', 'not_required']
                ).exclude(status='failed').order_by('created_at').select_for_update().first()
                
                if video:
                    video.hls_status = 'processing'
                    video.status = 'processing'
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

    logger.info("Finished prioritized transcoder cycle.")
