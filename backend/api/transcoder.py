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

class VideoProcessor:
    @staticmethod
    def probe_video(video_path):
        """Runs ffprobe to retrieve duration, width, height, and audio presence."""
        try:
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                '-show_streams',
                video_path
            ]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            data = json.loads(result.stdout)
            
            # Find video stream
            video_stream = next((stream for stream in data.get('streams', []) if stream.get('codec_type') == 'video'), None)
            audio_stream = next((stream for stream in data.get('streams', []) if stream.get('codec_type') == 'audio'), None)
            
            duration = float(data.get('format', {}).get('duration', 0.0))
            if duration <= 0 and video_stream:
                duration = float(video_stream.get('duration', 0.0))
                
            width = int(video_stream.get('width', 0)) if video_stream else 0
            height = int(video_stream.get('height', 0)) if video_stream else 0
            has_audio = audio_stream is not None
            
            return {
                'duration': duration,
                'width': width,
                'height': height,
                'has_audio': has_audio
            }
        except Exception as e:
            logger.error(f"Failed to probe video {video_path}: {e}")
            raise

    @staticmethod
    def generate_thumbnail(video_path, target_dir, midpoint):
        """Generates a high-quality thumbnail image using FFmpeg."""
        thumbnail_path = os.path.join(target_dir, 'thumbnail.jpg')
        cmd = [
            'ffmpeg', '-y',
            '-ss', str(midpoint),
            '-i', video_path,
            '-vframes', '1',
            '-q:v', '2',
            thumbnail_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            logger.error(f"Failed to generate thumbnail: {result.stderr.decode()}")
            raise Exception("FFmpeg thumbnail generation failed")

    @staticmethod
    def generate_preview(video_path, target_dir, start_time):
        """Generates a short (5s), high-quality silent MP4 preview clip for hover play."""
        preview_path = os.path.join(target_dir, 'preview.mp4')
        cmd = [
            'ffmpeg', '-y',
            '-ss', str(start_time),
            '-i', video_path,
            '-t', '5',         # 5 seconds duration (fast load)
            '-an',             # Remove audio
            '-vf', 'scale=854:480', # High detail resolution
            '-c:v', 'libx264',
            '-crf', '18',      # Visually lossless quality
            '-pix_fmt', 'yuv420p',
            '-profile:v', 'high',
            '-level', '4.0',
            preview_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            logger.error(f"Failed to generate preview: {result.stderr.decode()}")
            raise Exception("FFmpeg preview generation failed")

    @staticmethod
    def generate_sprite_sheet(video_path, target_dir, duration):
        """Generates 160x90 sprite sheets tiled into 10x10 grids, plus metadata."""
        # Frame every 2 seconds for smooth scrubbing preview
        interval = 2
        columns = 10
        rows = 10
        
        # Output template
        sprite_template = os.path.join(target_dir, 'sprite_%03d.jpg')
        
        # FFmpeg tile command: scale each frame to 160x90, tile in 10x10 grid
        cmd = [
            'ffmpeg', '-y',
            '-i', video_path,
            '-vf', f'fps=1/{interval},scale=160:90,tile={columns}x{rows}',
            '-vsync', 'vfr',
            sprite_template
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            logger.error(f"Failed to generate sprite sheets: {result.stderr.decode()}")
            raise Exception("FFmpeg sprite sheet generation failed")
            
        # Write metadata file for front-end parsing
        metadata = {
            'interval': interval,
            'columns': columns,
            'rows': rows,
            'width': 160,
            'height': 90
        }
        with open(os.path.join(target_dir, 'sprite_info.json'), 'w') as f:
            json.dump(metadata, f, indent=2)

    @classmethod
    def transcode_hls(cls, video, original_path, target_dir, info):
        """Transcodes a video file into adaptive multi-bitrate HLS streams."""
        duration = info['duration']
        height = info['height']
        has_audio = info['has_audio']
        
        # Output directory for HLS segments
        streams_dir = os.path.join(target_dir, 'streams')
        os.makedirs(streams_dir, exist_ok=True)
        
        # Define target profiles
        profiles = [
            {'name': '1080p', 'w': 1920, 'h': 1080, 'b_v': '4500k', 'b_a': '192k'},
            {'name': '720p', 'w': 1280, 'h': 720, 'b_v': '2500k', 'b_a': '128k'},
            {'name': '480p', 'w': 854, 'h': 480, 'b_v': '1000k', 'b_a': '96k'},
        ]
        
        # Filter profiles to only keep those smaller or equal to source resolution
        active_profiles = [p for p in profiles if p['h'] <= height]
        if not active_profiles:
            # Fallback to original resolution capped at 480p equivalent bitrate
            active_profiles = [{'name': f'{height}p', 'w': info['width'], 'h': height, 'b_v': '1000k', 'b_a': '96k'}]
            
        # Clean up any existing streams to ensure fresh transcode
        if os.path.exists(streams_dir):
            shutil.rmtree(streams_dir)
        os.makedirs(streams_dir, exist_ok=True)
        
        # Create subfolders for HLS playlist & segments
        for i in range(len(active_profiles)):
            os.makedirs(os.path.join(streams_dir, f'stream_{i}'), exist_ok=True)
            
        # Build multi-stream ffmpeg command
        cmd = ['ffmpeg', '-y', '-i', original_path, '-progress', '-']
        
        # Build filter_complex split and scale
        split_filter = f"[0:v]split={len(active_profiles)}"
        split_outputs = "".join(f"[v{i}]" for i in range(len(active_profiles)))
        filters = [f"{split_filter}{split_outputs}"]
        for i, profile in enumerate(active_profiles):
            filters.append(f"[v{i}]scale=w={profile['w']}:h={profile['h']}[v{i}out]")
        filter_complex = ";".join(filters)
        cmd += ['-filter_complex', filter_complex]
        
        var_stream_map_parts = []
        for i, profile in enumerate(active_profiles):
            cmd += ['-map', f'[v{i}out]']
            cmd += [f'-c:v:{i}', 'libx264', f'-b:v:{i}', profile['b_v']]
            cmd += [f'-maxrate:v:{i}', f"{int(profile['b_v'].replace('k', '')) * 1.1:.0f}k"]
            cmd += [f'-bufsize:v:{i}', f"{int(profile['b_v'].replace('k', '')) * 1.5:.0f}k"]
            
            if has_audio:
                cmd += ['-map', 'a:0', f'-c:a:{i}', 'aac', f'-b:a:{i}', profile['b_a']]
                var_stream_map_parts.append(f"v:{i},a:{i}")
            else:
                var_stream_map_parts.append(f"v:{i}")
                
        cmd += [
            '-f', 'hls',
            '-hls_time', '6',
            '-hls_playlist_type', 'event',
            '-master_pl_name', 'master.m3u8',
            '-var_stream_map', " ".join(var_stream_map_parts),
            '-hls_segment_filename', os.path.join(streams_dir, 'stream_%v', 'data%03d.ts'),
            os.path.join(streams_dir, 'stream_%v', 'playlist.m3u8')
        ]
        
        # Run subprocess and monitor progress
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        logs = []
        for line in process.stdout:
            logs.append(line)
            if 'out_time_us=' in line:
                try:
                    time_us = int(line.split('=')[1].strip())
                    time_s = time_us / 1000000.0
                    if duration > 0:
                        # HLS transcoding is 80% of total work, first 20% was thumbnails, previews, sprites
                        progress = 20.0 + (min(1.0, time_s / duration) * 79.0)
                        video.progress = round(progress, 1)
                        video.save(update_fields=['progress'])
                except Exception:
                    pass
                    
        process.wait()
        if process.returncode != 0:
            error_log = "".join(logs[-10:])
            raise Exception(f"FFmpeg HLS failed with exit code {process.returncode}. Log: {error_log}")
            
        # Write quality descriptions for HLS streams so frontend knows human-readable labels
        with open(os.path.join(streams_dir, 'metadata.json'), 'w') as f:
            json.dump({'streams': active_profiles}, f, indent=2)

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
            info = cls.probe_video(video.original_path)
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
            cls.generate_thumbnail(video.original_path, target_dir, midpoint)
            
            # 3. Sprite Sheet
            video.progress = 15.0
            video.save()
            cls.generate_sprite_sheet(video.original_path, target_dir, video.duration)
            
            # 4. Preview Clip
            video.progress = 20.0
            video.save()
            cls.generate_preview(video.original_path, target_dir, start_time)
            
            # 5. HLS Transcoding
            cls.transcode_hls(video, video.original_path, target_dir, info)
            
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

