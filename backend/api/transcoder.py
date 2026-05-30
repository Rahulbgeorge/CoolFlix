import os
import json
import shutil
import logging
import subprocess
from django.conf import settings
from django.utils.text import slugify
from .models import Video, Setting

logger = logging.getLogger(__name__)

from .infrastructure.transcoder import FFmpegTranscoder

class VideoProcessor:
    """
    A Django-specific wrapper that coordinates the database operations and states
    during a video's transcode pipeline, delegating actual FFmpeg operations
    to the decoupled FFmpegTranscoder infrastructure class.
    """

    @classmethod
    def get_target_dir(cls, video):
        """Resolves target folder dynamically from settings configuration."""
        try:
            output_loc = Setting.objects.get(key='output_loc').value
        except Setting.DoesNotExist:
            try:
                source_loc = Setting.objects.get(key='source_loc').value
                output_loc = os.path.join(source_loc, 'streamable')
            except Setting.DoesNotExist:
                output_loc = os.path.join(settings.MEDIA_ROOT, 'streamable')
        return os.path.join(output_loc, video.slug)

    @classmethod
    def process_hls_only(cls, video_id):
        """Processes only the HLS transcoding stage."""
        try:
            video = Video.objects.get(id=video_id)
        except Video.DoesNotExist:
            return
            
        try:
            # 1. Probe video metadata
            info = FFmpegTranscoder.probe_video(video.original_path)
            video.duration = info['duration']
            video.width = info['width']
            video.height = info['height']
            video.save()
            
            target_dir = cls.get_target_dir(video)
            os.makedirs(target_dir, exist_ok=True)
            
            def hls_progress_callback(percent):
                # HLS transcoding is mapped to the final third (66.7% - 100%) of total progress
                total_progress = 66.7 + (percent * 0.333)
                video.progress = round(total_progress, 1)
                video.save(update_fields=['progress'])
                
            FFmpegTranscoder.transcode_hls(
                video_path=video.original_path,
                target_dir=target_dir,
                width=video.width,
                height=video.height,
                duration=video.duration,
                has_audio=info['has_audio'],
                progress_callback=hls_progress_callback,
                target_quality=video.transcode_target,
                video_codec=info.get('video_codec', ''),
                audio_codec=info.get('audio_codec', ''),
                audio_tracks=info.get('audio_tracks', [])
            )
            
            video.hls_status = 'completed'
            video.status = 'completed'
            video.progress = 100.0
            video.save()
            logger.info(f"Successfully processed HLS for video: {video.title}")
            
        except Exception as e:
            logger.exception(f"Failed HLS generation for video {video.title}")
            video.status = 'failed'
            video.hls_status = 'failed'
            video.error_message = str(e)
            video.save()
            raise

    @classmethod
    def process_sprite_only(cls, video_id):
        """Processes only the sprite sheet generation stage."""
        try:
            video = Video.objects.get(id=video_id)
        except Video.DoesNotExist:
            return
            
        try:
            target_dir = cls.get_target_dir(video)
            os.makedirs(target_dir, exist_ok=True)
            
            video.progress = 5.0
            video.save(update_fields=['progress'])
            
            FFmpegTranscoder.generate_sprite_sheet(video.original_path, target_dir, video.duration)
            
            video.sprite_status = 'completed'
            video.progress = 33.3 if video.hls_required else 50.0
            video.save()
            logger.info(f"Successfully processed sprite sheet for video: {video.title}")
            
        except Exception as e:
            logger.exception(f"Failed sprite sheet generation for video {video.title}")
            video.status = 'failed'
            video.sprite_status = 'failed'
            video.error_message = str(e)
            video.save()
            raise

    @classmethod
    def process_preview_only(cls, video_id):
        """Processes only the thumbnail and preview clip generation stage."""
        try:
            video = Video.objects.get(id=video_id)
        except Video.DoesNotExist:
            return
            
        try:
            target_dir = cls.get_target_dir(video)
            os.makedirs(target_dir, exist_ok=True)
            
            video.progress = 35.0 if video.hls_required else 50.0
            video.save(update_fields=['progress'])
            
            # Select random preview start point between 15% and 80% to avoid title cards
            import random
            if video.duration > 15:
                start_time = random.uniform(video.duration * 0.15, video.duration * 0.80)
            elif video.duration > 5:
                start_time = random.uniform(0, video.duration - 5)
            else:
                start_time = 0.0
                
            midpoint = video.duration * 0.3 if video.duration > 10 else 1.0
            
            FFmpegTranscoder.generate_thumbnail(video.original_path, target_dir, midpoint)
            FFmpegTranscoder.generate_preview(video.original_path, target_dir, start_time)
            
            video.preview_status = 'completed'
            video.status = 'completed'
            if not video.hls_required:
                video.hls_status = 'skipped'
                video.progress = 100.0
            else:
                video.progress = 66.7
            video.save()
            logger.info(f"Successfully processed preview & thumbnail for video: {video.title}")
            
        except Exception as e:
            logger.exception(f"Failed preview/thumbnail generation for video {video.title}")
            video.status = 'failed'
            video.preview_status = 'failed'
            video.error_message = str(e)
            video.save()
            raise


    @classmethod
    def process_video_pipeline(cls, video_id):
        """Full sequential execution of the pipeline (backwards compatible)."""
        try:
            video = Video.objects.get(id=video_id)
        except Video.DoesNotExist:
            return
            
        video.status = 'processing'
        video.sprite_status = 'pending'
        video.preview_status = 'pending'
        video.hls_status = 'pending'
        video.progress = 5.0
        video.error_message = None
        video.save()
        
        cls.process_sprite_only(video_id)
        
        video.refresh_from_db()
        if video.status != 'failed':
            video.preview_status = 'processing'
            video.save(update_fields=['preview_status'])
            cls.process_preview_only(video_id)
            
        video.refresh_from_db()
        if video.status != 'failed':
            video.hls_status = 'processing'
            video.save(update_fields=['hls_status'])
            cls.process_hls_only(video_id)



