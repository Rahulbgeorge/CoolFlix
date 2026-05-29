import os
import json
import shutil
import logging
import subprocess
from typing import List, Optional, Callable, Dict, Any

logger = logging.getLogger(__name__)

class FFmpegTranscoder:
    """
    A reusable utility class to handle all FFmpeg and FFprobe tasks:
    - Probing video files for stream metadata (dimensions, audio, duration)
    - Generating static midpoint thumbnails
    - Creating short, silent preview video clips
    - Building tiled sprite sheets for interactive timeline scrubbing
    - Transcoding videos into adaptive multi-bitrate HLS streams with progress tracking
    """

    @staticmethod
    def probe_video(video_path: str) -> Dict[str, Any]:
        """
        Runs ffprobe to retrieve duration, width, height, and audio presence.
        Returns a dictionary containing:
        - duration (float): video duration in seconds
        - width (int): width of video stream in pixels
        - height (int): height of video stream in pixels
        - has_audio (bool): True if audio stream exists, False otherwise
        """
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
            video_codec = video_stream.get('codec_name', '').lower() if video_stream else ''
            audio_codec = audio_stream.get('codec_name', '').lower() if audio_stream else ''
            
            return {
                'duration': duration,
                'width': width,
                'height': height,
                'has_audio': has_audio,
                'video_codec': video_codec,
                'audio_codec': audio_codec
            }
        except Exception as e:
            logger.error(f"Failed to probe video {video_path}: {e}")
            raise

    @staticmethod
    def generate_thumbnail(video_path: str, target_dir: str, midpoint: float) -> str:
        """
        Generates a high-quality thumbnail image using FFmpeg at the specified midpoint timestamp.
        Returns the path of the generated thumbnail image on disk.
        """
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
        return thumbnail_path

    @staticmethod
    def generate_preview(video_path: str, target_dir: str, start_time: float, duration: float = 5.0) -> str:
        """
        Generates a short, high-quality silent MP4 preview clip for hover play.
        Returns the path of the generated preview clip on disk.
        """
        preview_path = os.path.join(target_dir, 'preview.mp4')
        cmd = [
            'ffmpeg', '-y',
            '-ss', str(start_time),
            '-i', video_path,
            '-t', str(duration),         # preview duration (default 5 seconds)
            '-an',                       # Remove audio
            '-vf', 'scale=854:480',      # scaled down to 480p equivalent
            '-c:v', 'libx264',
            '-crf', '18',                # Visually lossless quality
            '-pix_fmt', 'yuv420p',
            '-profile:v', 'high',
            '-level', '4.0',
            preview_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            logger.error(f"Failed to generate preview: {result.stderr.decode()}")
            raise Exception("FFmpeg preview generation failed")
        return preview_path

    @staticmethod
    def generate_sprite_sheet(video_path: str, target_dir: str, duration: float, interval: int = 2) -> Dict[str, Any]:
        """
        Generates tiled sprite sheets (160x90 frames tiled into 10x10 grids)
        at intervals of every N seconds, plus a metadata descriptor file.
        Returns the dictionary metadata format.
        """
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
            
        return metadata

    @staticmethod
    def detect_gpu_support() -> bool:
        """
        Detects if NVIDIA NVENC H.264 encoder is available on the system.
        """
        try:
            cmd = [
                'ffmpeg', '-y',
                '-f', 'lavfi', '-i', 'color=c=black:s=16x16:d=0.1',
                '-c:v', 'h264_nvenc',
                '-f', 'null', '-'
            ]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
            return result.returncode == 0
        except Exception:
            return False

    @staticmethod
    def _execute_ffmpeg_command(cmd: List[str], duration: float, progress_callback: Optional[Callable[[float], None]]) -> None:
        logger.info(f"Executing FFmpeg command: {' '.join(cmd)}")
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
                    if duration > 0 and progress_callback:
                        progress = min(100.0, (time_s / duration) * 100.0)
                        progress_callback(progress)
                except Exception:
                    pass
                    
        process.wait()
        if process.returncode != 0:
            error_log = "".join(logs[-15:])
            raise Exception(f"FFmpeg failed with exit code {process.returncode}. Log: {error_log}")

    @classmethod
    def transcode_hls(
        cls,
        video_path: str,
        target_dir: str,
        width: int,
        height: int,
        duration: float,
        has_audio: bool,
        progress_callback: Optional[Callable[[float], None]] = None,
        target_quality: str = 'original',
        video_codec: str = '',
        audio_codec: str = ''
    ) -> List[Dict[str, Any]]:
        """
        Transcodes or copies a video file into a streamable single-variant HLS stream.
        Optimally uses hardware GPU/CUDA acceleration if available and falls back to CPU.
        """
        if not video_codec or not audio_codec:
            try:
                info = cls.probe_video(video_path)
                video_codec = info.get('video_codec', '')
                audio_codec = info.get('audio_codec', '')
            except Exception:
                pass

        streams_dir = os.path.join(target_dir, 'streams')
        if os.path.exists(streams_dir):
            shutil.rmtree(streams_dir)
        os.makedirs(streams_dir, exist_ok=True)
        os.makedirs(os.path.join(streams_dir, 'stream_0'), exist_ok=True)

        # 1. Determine if we can do Stream Copy (only when target is original, video is h264, audio is aac or absent)
        can_copy_video = (target_quality == 'original' and video_codec == 'h264')
        can_copy_audio = (target_quality == 'original' and (audio_codec == 'aac' or not has_audio))
        is_stream_copy = can_copy_video and can_copy_audio

        if is_stream_copy:
            logger.info("Codes are compatible (H264/AAC). Initiating stream copying...")
            cmd = ['ffmpeg', '-y', '-i', video_path, '-progress', '-']
            cmd += ['-map', '0:v:0', '-c:v', 'copy']
            if has_audio:
                cmd += ['-map', '0:a:0', '-c:a', 'copy']
                var_stream_map = "v:0,a:0"
            else:
                var_stream_map = "v:0"

            cmd += [
                '-f', 'hls',
                '-hls_time', '6',
                '-hls_playlist_type', 'event',
                '-master_pl_name', 'master.m3u8',
                '-var_stream_map', var_stream_map,
                '-hls_segment_filename', os.path.join(streams_dir, 'stream_%v', 'data%03d.ts'),
                os.path.join(streams_dir, 'stream_%v', 'playlist.m3u8')
            ]
            
            cls._execute_ffmpeg_command(cmd, duration, progress_callback)
            active_profiles = [{'name': 'Original (Copy)', 'w': width, 'h': height, 'b_v': 'original', 'b_a': 'original'}]
            
            with open(os.path.join(streams_dir, 'metadata.json'), 'w') as f:
                json.dump({'streams': active_profiles}, f, indent=2)
            return active_profiles

        # 2. Transcoding is required (either because resolution is specified or codecs are incompatible)
        profile_map = {
            '1080p': {'name': '1080p', 'w': 1920, 'h': 1080, 'b_v': '4500k', 'b_a': '192k'},
            '720p': {'name': '720p', 'w': 1280, 'h': 720, 'b_v': '2500k', 'b_a': '128k'},
            '480p': {'name': '480p', 'w': 854, 'h': 480, 'b_v': '1000k', 'b_a': '96k'},
        }

        if target_quality in profile_map:
            prof = profile_map[target_quality]
            if height > 0 and prof['h'] > height:
                # Cap at original height to avoid upscaling
                target_w = width
                target_h = height
                target_bv = prof['b_v']
                target_ba = prof['b_a']
                profile_name = f"Original ({height}p)"
            else:
                target_w = prof['w']
                target_h = prof['h']
                target_bv = prof['b_v']
                target_ba = prof['b_a']
                profile_name = prof['name']
        else:
            # original quality but needs encoding due to non-H.264/AAC codec
            target_w = width
            target_h = height
            if height >= 1080:
                target_bv, target_ba = '4500k', '192k'
            elif height >= 720:
                target_bv, target_ba = '2500k', '128k'
            else:
                target_bv, target_ba = '1000k', '96k'
            profile_name = 'Original'

        active_profiles = [{'name': profile_name, 'w': target_w, 'h': target_h, 'b_v': target_bv, 'b_a': target_ba}]
        has_gpu = cls.detect_gpu_support()

        # Build GPU command (CUDA decoding + NVENC encoding)
        gpu_cmd = []
        if has_gpu:
            gpu_cmd = ['ffmpeg', '-y', '-hwaccel', 'cuda', '-i', video_path, '-progress', '-']
            gpu_vf = []
            if target_h != height or target_w != width:
                gpu_vf.append(f"scale=-2:{target_h}")
            else:
                # Ensure width/height are even for h264
                if target_w % 2 != 0 or target_h % 2 != 0:
                    gpu_vf.append("scale=trunc(iw/2)*2:trunc(ih/2)*2")
            if gpu_vf:
                gpu_cmd += ['-vf', ",".join(gpu_vf)]
            
            gpu_cmd += ['-map', '0:v:0', '-c:v', 'h264_nvenc', '-preset', 'fast', '-b:v', target_bv]
            gpu_cmd += ['-maxrate:v', f"{int(target_bv.replace('k', '')) * 1.1:.0f}k"]
            gpu_cmd += ['-bufsize:v', f"{int(target_bv.replace('k', '')) * 1.5:.0f}k"]
            
            if has_audio:
                gpu_cmd += ['-map', '0:a:0', '-c:a', 'aac', '-b:a', target_ba]
                var_stream_map = "v:0,a:0"
            else:
                var_stream_map = "v:0"
                
            gpu_cmd += [
                '-f', 'hls',
                '-hls_time', '6',
                '-hls_playlist_type', 'event',
                '-master_pl_name', 'master.m3u8',
                '-var_stream_map', var_stream_map,
                '-hls_segment_filename', os.path.join(streams_dir, 'stream_%v', 'data%03d.ts'),
                os.path.join(streams_dir, 'stream_%v', 'playlist.m3u8')
            ]

        # Build CPU command (fallback or standard)
        cpu_cmd = ['ffmpeg', '-y', '-i', video_path, '-progress', '-']
        cpu_vf = []
        if target_h != height or target_w != width:
            cpu_vf.append(f"scale=-2:{target_h}")
        else:
            if target_w % 2 != 0 or target_h % 2 != 0:
                cpu_vf.append("scale=trunc(iw/2)*2:trunc(ih/2)*2")
        if cpu_vf:
            cpu_cmd += ['-vf', ",".join(cpu_vf)]
            
        cpu_cmd += ['-map', '0:v:0', '-c:v', 'libx264', '-preset', 'veryfast', '-b:v', target_bv]
        cpu_cmd += ['-maxrate:v', f"{int(target_bv.replace('k', '')) * 1.1:.0f}k"]
        cpu_cmd += ['-bufsize:v', f"{int(target_bv.replace('k', '')) * 1.5:.0f}k"]
        
        if has_audio:
            cpu_cmd += ['-map', '0:a:0', '-c:a', 'aac', '-b:a', target_ba]
            var_stream_map = "v:0,a:0"
        else:
            var_stream_map = "v:0"
            
        cpu_cmd += [
            '-f', 'hls',
            '-hls_time', '6',
            '-hls_playlist_type', 'event',
            '-master_pl_name', 'master.m3u8',
            '-var_stream_map', var_stream_map,
            '-hls_segment_filename', os.path.join(streams_dir, 'stream_%v', 'data%03d.ts'),
            os.path.join(streams_dir, 'stream_%v', 'playlist.m3u8')
        ]

        # Run with GPU first, fallback to CPU on any failure
        if has_gpu:
            try:
                logger.info("Attempting GPU/CUDA accelerated HLS transcoding...")
                cls._execute_ffmpeg_command(gpu_cmd, duration, progress_callback)
            except Exception as gpu_err:
                logger.warning(f"GPU transcoding failed: {gpu_err}. Falling back to CPU...")
                # Cleanup the directories first
                if os.path.exists(streams_dir):
                    shutil.rmtree(streams_dir)
                os.makedirs(streams_dir, exist_ok=True)
                os.makedirs(os.path.join(streams_dir, 'stream_0'), exist_ok=True)
                cls._execute_ffmpeg_command(cpu_cmd, duration, progress_callback)
        else:
            logger.info("GPU/CUDA acceleration not available. Running CPU transcoding...")
            cls._execute_ffmpeg_command(cpu_cmd, duration, progress_callback)

        with open(os.path.join(streams_dir, 'metadata.json'), 'w') as f:
            json.dump({'streams': active_profiles}, f, indent=2)
            
        return active_profiles
