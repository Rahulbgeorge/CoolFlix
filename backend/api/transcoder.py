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
    def process_streamable_copy(cls, video_id):
        """Processes the streamable copy generation stage (original conversion)."""
        try:
            video = Video.objects.get(id=video_id)
        except Video.DoesNotExist:
            return
            
        try:
            video.status = 'processing'
            video.streamable_copy_status = 'processing'
            video.save(update_fields=['status', 'streamable_copy_status'])
            
            # Ensure metadata is probed
            if video.duration == 0.0:
                info = FFmpegTranscoder.probe_video(video.original_path)
                video.duration = info['duration']
                video.width = info['width']
                video.height = info['height']
                video.save()
                
            target_dir = cls.get_target_dir(video)
            os.makedirs(target_dir, exist_ok=True)
            
            # Generate the streamable copy replacing the symlink
            FFmpegTranscoder.convert_original_streamable(video.original_path, target_dir)
            
            video.streamable_copy_status = 'completed'
            video.save(update_fields=['streamable_copy_status'])
            logger.info(f"Successfully generated streamable copy for video: {video.title}")
        except Exception as e:
            logger.exception(f"Failed streamable copy generation for video {video.title}")
            video.status = 'failed'
            video.streamable_copy_status = 'failed'
            video.error_message = str(e)
            video.save()
            raise

    @classmethod
    def process_hls_only(cls, video_id):
        """Processes only the HLS transcoding stage based on requested quality profile."""
        try:
            video = Video.objects.get(id=video_id)
        except Video.DoesNotExist:
            return
            
        try:
            info = FFmpegTranscoder.probe_video(video.original_path)
            video.duration = info['duration']
            video.width = info['width']
            video.height = info['height']
            video.save()
            
            target_dir = cls.get_target_dir(video)
            os.makedirs(target_dir, exist_ok=True)
            
            def hls_progress_callback(percent):
                total_progress = 66.7 + (percent * 0.333)
                video.progress = round(total_progress, 1)
                video.save(update_fields=['progress'])
                
            if video.transcode_target == '480p':
                FFmpegTranscoder.transcode_480p(
                    video_path=video.original_path,
                    target_dir=target_dir,
                    duration=video.duration,
                    has_audio=info['has_audio'],
                    progress_callback=hls_progress_callback,
                    audio_tracks=info.get('audio_tracks', [])
                )
            elif video.transcode_target == '720p':
                FFmpegTranscoder.transcode_720p(
                    video_path=video.original_path,
                    target_dir=target_dir,
                    duration=video.duration,
                    has_audio=info['has_audio'],
                    progress_callback=hls_progress_callback,
                    audio_tracks=info.get('audio_tracks', [])
                )
            elif video.transcode_target == '1080p':
                FFmpegTranscoder.transcode_1080p(
                    video_path=video.original_path,
                    target_dir=target_dir,
                    duration=video.duration,
                    has_audio=info['has_audio'],
                    progress_callback=hls_progress_callback,
                    audio_tracks=info.get('audio_tracks', [])
                )
            else:
                # original quality: package into HLS via stream copy (quick & no re-encoding)
                FFmpegTranscoder.package_original_hls(
                    video_path=video.original_path,
                    target_dir=target_dir,
                    duration=video.duration,
                    has_audio=info['has_audio'],
                    progress_callback=hls_progress_callback,
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
            if video.duration == 0.0:
                info = FFmpegTranscoder.probe_video(video.original_path)
                video.duration = info['duration']
                video.width = info['width']
                video.height = info['height']
                video.save()
                
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

            target_dir = cls.get_target_dir(video)
            os.makedirs(target_dir, exist_ok=True)
            midpoint = video.duration * 0.3 if video.duration > 10 else 1.0
            FFmpegTranscoder.generate_thumbnail(video.original_path, target_dir, midpoint)
            
            video.preview_clip_status = 'completed'
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
        """Processes only the thumbnail and actual physical 5s 480p preview file generation stage."""
        try:
            video = Video.objects.get(id=video_id)
        except Video.DoesNotExist:
            return
            
        try:
            target_dir = cls.get_target_dir(video)
            os.makedirs(target_dir, exist_ok=True)
            
            midpoint = video.duration * 0.3 if video.duration > 10 else 1.0
            FFmpegTranscoder.generate_thumbnail(video.original_path, target_dir, midpoint)
            
            if video.preview_status in ('pending', 'processing'):
                preview_clip = video.clips.filter(category='Preview').first()
                start_time = preview_clip.start_time if preview_clip else (video.duration * 0.3)
                
                # Extract preview from the streamable faststart original.mp4 copy
                streamable_path = os.path.join(target_dir, 'original.mp4')
                input_path = streamable_path if os.path.exists(streamable_path) else video.original_path
                
                FFmpegTranscoder.generate_preview(input_path, target_dir, start_time)
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
            logger.info(f"Successfully processed actual 5s 480p preview file and thumbnail for video: {video.title}")
            
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
        video.streamable_copy_status = 'pending'
        video.preview_clip_status = 'pending'
        video.sprite_status = 'pending'
        video.preview_status = 'pending'
        video.hls_status = 'pending'
        video.progress = 1.0
        video.error_message = None
        video.save()
        
        cls.process_streamable_copy(video_id)
        
        video.refresh_from_db()
        if video.status != 'failed':
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



