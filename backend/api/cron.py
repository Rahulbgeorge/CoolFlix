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
    Video.objects.filter(preview_clip_status='processing').update(preview_clip_status='pending')
    Video.objects.filter(preview_status='processing').update(preview_status='pending')
    

def run_fast_pipeline_cron():
    """
    Cron worker task that handles only fast, priority operations (20-30s total):
    1. Original streamable copy conversion (~20s).
    2. Quick database preview clip & thumbnail generation (instant).
    3. Physical 5s 480p silent preview clip generation (~2s).
    4. HLS original copy (instant).
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    lock_file_path = os.path.join(base_dir, 'fast_pipeline.lock')
    
    lock_file = open(lock_file_path, 'w')
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except IOError:
        logger.info("Another instance of the fast pipeline is already running. Exiting...")
        return

    logger.info("Acquired fast pipeline lock. Running fast tasks...")
    
    # Recover stalled jobs
    try:
        Video.objects.filter(preview_clip_status='processing').update(preview_clip_status='pending')
        Video.objects.filter(preview_status='processing').update(preview_status='pending')
    except Exception as e:
        logger.error(f"Error resetting stalled fast tasks: {e}")

    # 1. First Priority: Quick preview clip & thumbnail metadata
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
                    video.progress = 5.0
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

    # 2. Second Priority: Physical 5s 480p silent preview clip
    while True:
        video_id = None
        try:
            with transaction.atomic():
                video = Video.objects.filter(
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
            logger.info(f"Running Physical 5s 480p Preview generation for video ID {video_id}...")
            VideoProcessor.process_preview_only(video_id)
        except Exception as e:
            logger.error(f"Failed Physical Preview generation for video ID {video_id}: {e}")

    # 3. Third Priority: Original HLS VOD packaging (stream copy)
    while True:
        video_id = None
        try:
            with transaction.atomic():
                video = Video.objects.filter(
                    hls_status='pending',
                    hls_required=True,
                    transcode_target='original'
                ).exclude(status='failed').order_by('created_at').select_for_update().first()
                
                if video:
                    video.hls_status = 'processing'
                    video.status = 'processing'
                    video.save()
                    video_id = video.id
        except Exception as e:
            logger.error(f"Error fetching pending original HLS task: {e}")
            break
            
        if not video_id:
            break
            
        try:
            logger.info(f"Running Original HLS generation for video ID {video_id}...")
            VideoProcessor.process_hls_only(video_id)
        except Exception as e:
            logger.error(f"Failed Original HLS generation for video ID {video_id}: {e}")

    logger.info("Finished fast pipeline cycle.")


def run_sprite_cron():
    """
    Cron worker task that handles heavy or sprite-related operations:
    1. Sprite sheet generation (Priority 1, with JPEG qscale size optimization).
    2. Heavy HLS adaptive transcodes (Priority 2, non-original qualities).
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    lock_file_path = os.path.join(base_dir, 'sprite_generator.lock')
    
    lock_file = open(lock_file_path, 'w')
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except IOError:
        logger.info("Another instance of the sprite generator is already running. Exiting...")
        return

    logger.info("Acquired sprite generator lock. Running sprite and HLS transcodes...")
    
    # Recover stalled jobs
    try:
        Video.objects.filter(sprite_status='processing').update(sprite_status='pending')
        Video.objects.filter(hls_status='processing').update(hls_status='pending')
    except Exception as e:
        logger.error(f"Error resetting stalled sprite/HLS tasks: {e}")

    # 1. First Priority: Lightweight timeline scrub Sprite Sheets
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
                    video.progress = 10.0
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

    # 2. Second Priority: Heavy HLS adaptive transcodes (only for targets that require encoding)
    while True:
        video_id = None
        try:
            with transaction.atomic():
                video = Video.objects.filter(
                    hls_status='pending',
                    hls_required=True,
                    sprite_status='completed',
                    preview_status__in=['completed', 'not_required']
                ).exclude(status='failed').exclude(transcode_target='original').order_by('created_at').select_for_update().first()
                
                if video:
                    video.hls_status = 'processing'
                    video.status = 'processing'
                    video.save()
                    video_id = video.id
        except Exception as e:
            logger.error(f"Error fetching pending HLS transcode task: {e}")
            break
            
        if not video_id:
            break
            
        try:
            logger.info(f"Running HLS generation for video ID {video_id}...")
            VideoProcessor.process_hls_only(video_id)
        except Exception as e:
            logger.error(f"Failed HLS generation for video ID {video_id}: {e}")

    logger.info("Finished sprite generator cycle.")


def run_transcoder_cron():
    """Backwards compatible single cron command that executes both cron subtasks sequentially."""
    run_fast_pipeline_cron()
    run_sprite_cron()
