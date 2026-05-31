import os
import json
import shutil
import logging
import subprocess
from django.conf import settings
from django.utils.text import slugify
from .models import Video, Setting, VideoClip

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
            
            # Probe metadata if duration is not set (e.g. if HLS stage is bypassed)
            if video.duration == 0.0:
                info = FFmpegTranscoder.probe_video(video.original_path)
                video.duration = info['duration']
                video.width = info['width']
                video.height = info['height']
                video.save()
            
            video.progress = 5.0
            video.save(update_fields=['progress'])
            
            FFmpegTranscoder.generate_sprite_sheet(video.original_path, target_dir, video.duration)
            
            video.sprite_status = 'completed'
            if video.preview_status != 'pending' and not video.hls_required:
                video.status = 'completed'
                video.progress = 100.0
            elif video.preview_status != 'pending' and video.hls_required:
                video.progress = 66.7
            else:
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
    def process_preview_clip_only(cls, video_id):
        """Processes only the quick database preview clip generation stage."""
        try:
            video = Video.objects.get(id=video_id)
        except Video.DoesNotExist:
            return
            
        try:
            # Probe metadata if duration is not set (safety fallback)
            if video.duration == 0.0:
                info = FFmpegTranscoder.probe_video(video.original_path)
                video.duration = info['duration']
                video.width = info['width']
                video.height = info['height']
                video.save()
                
            # Select random preview start point between 15% and 80% to avoid title cards
            import random
            if video.duration > 15:
                start_time = random.uniform(video.duration * 0.15, video.duration * 0.80)
            elif video.duration > 5:
                start_time = random.uniform(0, video.duration - 5)
            else:
                start_time = 0.0
                
            VideoClip.objects.get_or_create(
                video=video,
                category="Preview",
                defaults={
                    'name': "Preview Clip",
                    'start_time': round(start_time, 1),
                    'end_time': round(start_time + 5.0, 1)
                }
            )

            # Extract the thumbnail instantly so the cover image is ready
            target_dir = cls.get_target_dir(video)
            os.makedirs(target_dir, exist_ok=True)
            midpoint = video.duration * 0.3 if video.duration > 10 else 1.0
            FFmpegTranscoder.generate_thumbnail(video.original_path, target_dir, midpoint)
            
            video.preview_clip_status = 'completed'
            # Progress is set to a baseline of 5.0% since database preview clip & thumbnail are immediate
            video.progress = 5.0
            video.save()
            logger.info(f"Successfully processed preview database clip for video: {video.title}")
            
        except Exception as e:
            logger.exception(f"Failed database preview clip generation for video {video.title}")
            video.status = 'failed'
            video.preview_clip_status = 'failed'
            video.error_message = str(e)
            video.save()
            raise

    @classmethod
    def process_preview_only(cls, video_id):
        """Processes only the thumbnail and actual physical preview file generation stage."""
        try:
            video = Video.objects.get(id=video_id)
        except Video.DoesNotExist:
            return
            
        try:
            target_dir = cls.get_target_dir(video)
            os.makedirs(target_dir, exist_ok=True)
            
            midpoint = video.duration * 0.3 if video.duration > 10 else 1.0
            FFmpegTranscoder.generate_thumbnail(video.original_path, target_dir, midpoint)
            
            # Slice physical preview clip only if preview_status is pending or processing
            if video.preview_status in ('pending', 'processing'):
                # Read range from database Preview clip if it exists, otherwise select a new one
                preview_clip = video.clips.filter(category='Preview').first()
                start_time = preview_clip.start_time if preview_clip else (video.duration * 0.3)
                FFmpegTranscoder.generate_preview(video.original_path, target_dir, start_time)
                video.preview_status = 'completed'
            else:
                video.preview_status = 'not_required'
                
            video.status = 'completed'
            if not video.hls_required:
                video.hls_status = 'skipped'
                video.progress = 100.0
            else:
                video.progress = 66.7
            video.save()
            logger.info(f"Successfully processed actual preview file and thumbnail for video: {video.title}")
            
        except Exception as e:
            logger.exception(f"Failed physical preview/thumbnail generation for video {video.title}")
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
        video.preview_clip_status = 'pending'
        video.sprite_status = 'pending'
        video.preview_status = 'not_required'
        video.hls_status = 'pending'
        video.progress = 1.0
        video.error_message = None
        video.save()
        
        cls.process_preview_clip_only(video_id)
        
        video.refresh_from_db()
        if video.status != 'failed':
            video.sprite_status = 'processing'
            video.save(update_fields=['sprite_status'])
            cls.process_sprite_only(video_id)
            
        video.refresh_from_db()
        if video.status != 'failed':
            video.preview_status = 'processing'
            video.save(update_fields=['preview_status'])
            cls.process_preview_only(video_id)
            
        video.refresh_from_db()
        if video.status != 'failed' and video.hls_required:
            video.hls_status = 'processing'
            video.save(update_fields=['hls_status'])
            cls.process_hls_only(video_id)



