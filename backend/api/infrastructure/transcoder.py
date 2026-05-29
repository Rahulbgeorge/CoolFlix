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

    @classmethod
    def transcode_hls(
        cls,
        video_path: str,
        target_dir: str,
        width: int,
        height: int,
        duration: float,
        has_audio: bool,
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> List[Dict[str, Any]]:
        """
        Transcodes a video file into adaptive multi-bitrate HLS streams.
        Optionally takes a progress_callback function that is called with progress percentage (0.0 to 100.0).
        """
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
            active_profiles = [{'name': f'{height}p', 'w': width, 'h': height, 'b_v': '1000k', 'b_a': '96k'}]
            
        # Clean up any existing streams to ensure fresh transcode
        if os.path.exists(streams_dir):
            shutil.rmtree(streams_dir)
        os.makedirs(streams_dir, exist_ok=True)
        
        # Create subfolders for HLS playlist & segments
        for i in range(len(active_profiles)):
            os.makedirs(os.path.join(streams_dir, f'stream_{i}'), exist_ok=True)
            
        # Build multi-stream ffmpeg command
        cmd = ['ffmpeg', '-y', '-i', video_path, '-progress', '-']
        
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
                    if duration > 0 and progress_callback:
                        progress = min(100.0, (time_s / duration) * 100.0)
                        progress_callback(progress)
                except Exception:
                    pass
                    
        process.wait()
        if process.returncode != 0:
            error_log = "".join(logs[-10:])
            raise Exception(f"FFmpeg HLS failed with exit code {process.returncode}. Log: {error_log}")
            
        # Write quality descriptions for HLS streams so frontend knows human-readable labels
        with open(os.path.join(streams_dir, 'metadata.json'), 'w') as f:
            json.dump({'streams': active_profiles}, f, indent=2)
            
        return active_profiles
