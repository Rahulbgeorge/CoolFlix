import os
import json
import shutil
import logging
import subprocess
import threading
import queue
from django.conf import settings
from django.utils.text import slugify
from .models import Video, Setting

logger = logging.getLogger(__name__)

# Thread-safe queue for sequential video transcoding
transcode_queue = queue.Queue()
worker_thread = None

from .infrastructure.transcoder import FFmpegTranscoder

class VideoProcessor:
    """
    A Django-specific wrapper that coordinates the database operations and states
    during a video's transcode pipeline, delegating actual FFmpeg operations
    to the decoupled FFmpegTranscoder infrastructure class.
    """

    @classmethod
    def process_video_pipeline(cls, video_id):
        """Full pipeline execution for a single video."""
        try:
            video = Video.objects.get(id=video_id)
        except Video.DoesNotExist:
            return
            
        video.status = 'processing'
        video.progress = 5.0
        video.error_message = None
        video.save()
        
        try:
            # 1. Probe video metadata
            info = FFmpegTranscoder.probe_video(video.original_path)
            video.duration = info['duration']
            video.width = info['width']
            video.height = info['height']
            video.save()
            
            # Setup folders dynamically from output_loc configuration
            try:
                output_loc = Setting.objects.get(key='output_loc').value
            except Setting.DoesNotExist:
                try:
                    source_loc = Setting.objects.get(key='source_loc').value
                    output_loc = os.path.join(source_loc, 'streamable')
                except Setting.DoesNotExist:
                    output_loc = os.path.join(settings.MEDIA_ROOT, 'streamable')
                    
            target_dir = os.path.join(output_loc, video.slug)
            
            if os.path.exists(target_dir):
                shutil.rmtree(target_dir)
            os.makedirs(target_dir, exist_ok=True)
            
            # Times for preview & thumbnail
            start_time = min(5.0, video.duration * 0.1)
            midpoint = video.duration * 0.3 if video.duration > 10 else 1.0
            
            # 2. Thumbnail
            video.progress = 10.0
            video.save()
            FFmpegTranscoder.generate_thumbnail(video.original_path, target_dir, midpoint)
            
            # 3. Sprite Sheet
            video.progress = 15.0
            video.save()
            FFmpegTranscoder.generate_sprite_sheet(video.original_path, target_dir, video.duration)
            
            # 4. Preview Clip
            video.progress = 20.0
            video.save()
            FFmpegTranscoder.generate_preview(video.original_path, target_dir, start_time)
            
            # 5. HLS Transcoding (using a callback to report database progress updates)
            def hls_progress_callback(percent):
                # HLS transcoding progress is mapped to the remaining 80% of pipeline progress
                total_progress = 20.0 + (percent * 0.79)
                video.progress = round(total_progress, 1)
                video.save(update_fields=['progress'])
                
            FFmpegTranscoder.transcode_hls(
                video_path=video.original_path,
                target_dir=target_dir,
                width=video.width,
                height=video.height,
                duration=video.duration,
                has_audio=info['has_audio'],
                progress_callback=hls_progress_callback
            )
            
            # Complete
            video.status = 'completed'
            video.progress = 100.0
            video.save()
            logger.info(f"Successfully processed video: {video.title}")
            
        except Exception as e:
            logger.exception(f"Failed to transcode video {video.title}")
            video.status = 'failed'
            video.error_message = str(e)
            video.save()

def start_worker():
    """Starts the background worker thread if not already running."""
    global worker_thread
    if worker_thread is None or not worker_thread.is_alive():
        worker_thread = threading.Thread(target=_worker_loop, name="TranscoderWorker", daemon=True)
        worker_thread.start()

def _worker_loop():
    """Background queue worker loop."""
    logger.info("Transcoder worker thread started.")
    
    # Re-enqueue any videos that were interrupted in the 'processing' or 'pending' state
    try:
        from django.db.utils import OperationalError
        pending_videos = Video.objects.filter(status__in=['pending', 'processing'])
        for v in pending_videos:
            if v.status == 'processing':
                v.status = 'pending'
                v.progress = 0.0
                v.save(update_fields=['status', 'progress'])
            transcode_queue.put(v.id)
            logger.info(f"Re-enqueued video {v.title} on startup.")
    except OperationalError:
        # DB might not be initialized yet
        pass
    except Exception as e:
        logger.error(f"Error re-enqueuing videos on worker startup: {e}")

    while True:
        try:
            video_id = transcode_queue.get()
            if video_id is None:
                break
            VideoProcessor.process_video_pipeline(video_id)
        except Exception as e:
            logger.error(f"Error in transcoder worker loop: {e}")
        finally:
            transcode_queue.task_done()

