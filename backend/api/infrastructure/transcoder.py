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
            audio_streams = [stream for stream in data.get('streams', []) if stream.get('codec_type') == 'audio']
            
            duration = float(data.get('format', {}).get('duration', 0.0))
            if duration <= 0 and video_stream:
                duration = float(video_stream.get('duration', 0.0))
                
            width = int(video_stream.get('width', 0)) if video_stream else 0
            height = int(video_stream.get('height', 0)) if video_stream else 0
            has_audio = len(audio_streams) > 0
            video_codec = video_stream.get('codec_name', '').lower() if video_stream else ''
            audio_codec = audio_streams[0].get('codec_name', '').lower() if has_audio else ''
            
            audio_tracks = []
            for idx, stream in enumerate(audio_streams):
                tags = stream.get('tags', {})
                lang = tags.get('language', 'und')
                title = tags.get('title', f"Audio Track {idx + 1}")
                audio_tracks.append({
                    'index': idx,
                    'stream_index': stream.get('index'),
                    'codec': stream.get('codec_name', '').lower(),
                    'language': lang,
                    'title': title
                })
            
            return {
                'duration': duration,
                'width': width,
                'height': height,
                'has_audio': has_audio,
                'video_codec': video_codec,
                'audio_codec': audio_codec,
                'audio_tracks': audio_tracks
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
        print(f"Executing FFmpeg command (Thumbnail): {' '.join(cmd)}")
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
        print(f"Executing FFmpeg command (Preview): {' '.join(cmd)}")
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
        
        # FFmpeg tile command: scale each frame to 160x90, tile in 10x10 grid with qscale compression to guarantee size <2MB
        cmd = [
            'ffmpeg', '-y',
            '-i', video_path,
            '-vf', f'fps=1/{interval},scale=160:90,tile={columns}x{rows}',
            '-qscale:v', '5',
            '-vsync', 'vfr',
            sprite_template
        ]
        print(f"Executing FFmpeg command (Sprite Sheet): {' '.join(cmd)}")
        log_path = os.path.join(target_dir, 'sprite_generation.log')
        try:
            with open(log_path, 'w') as log_file:
                result = subprocess.run(cmd, stdout=log_file, stderr=log_file)
        except Exception as e:
            logger.error(f"Failed to execute sprite command: {e}")
            raise
            
        if result.returncode != 0:
            try:
                with open(log_path, 'r') as log_file:
                    lines = log_file.readlines()
                    error_log = "".join(lines[-15:])
            except Exception:
                error_log = "Check sprite_generation.log inside target directory."
            logger.error(f"Failed to generate sprite sheets: {error_log}")
            raise Exception(f"FFmpeg sprite sheet generation failed. Log: {error_log}")
            
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
        cmd_str = ' '.join(cmd)
        print(f"Executing FFmpeg command (HLS Transcode): {cmd_str}")
        logger.info(f"Executing FFmpeg command: {cmd_str}")
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
    def convert_original_streamable(cls, video_path: str, target_dir: str) -> str:
        """
        Performs a fast stream copy of the original video file, moving the moov atom
        to the beginning (faststart) to make it easy to stream without transcoding.
        Completes in ~20 seconds.
        """
        output_path = os.path.join(target_dir, 'original.mp4')
        
        # If output_path is a symlink, remove it
        if os.path.islink(output_path):
            os.unlink(output_path)
        elif os.path.exists(output_path):
            try:
                os.remove(output_path)
            except Exception:
                pass

        cmd = [
            'ffmpeg', '-y',
            '-i', video_path,
            '-c', 'copy',
            '-map', '0',
            '-movflags', '+faststart',
            output_path
        ]
        print(f"Executing FFmpeg command (Original Conversion): {' '.join(cmd)}")
        logger.info(f"Executing FFmpeg command (Original Conversion): {' '.join(cmd)}")
        
        log_path = os.path.join(target_dir, 'original_conversion.log')
        try:
            with open(log_path, 'w') as log_file:
                result = subprocess.run(cmd, stdout=log_file, stderr=log_file)
        except Exception as e:
            logger.error(f"Failed to execute original conversion command: {e}")
            raise
            
        if result.returncode != 0:
            try:
                with open(log_path, 'r') as log_file:
                    lines = log_file.readlines()
                    error_log = "".join(lines[-15:])
            except Exception:
                error_log = "Check original_conversion.log inside target directory."
            logger.error(f"Failed to generate streamable copy: {error_log}")
            raise Exception(f"FFmpeg original conversion failed. Log: {error_log}")
            
        return output_path

    @classmethod
    def _transcode_to_hls_profile(
        cls,
        video_path: str,
        target_dir: str,
        target_w: int,
        target_h: int,
        target_bv: str,
        target_ba: str,
        profile_name: str,
        duration: float,
        has_audio: bool,
        progress_callback: Optional[Callable[[float], None]] = None,
        audio_tracks: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Generic internal HLS transcoder supporting single-profile target (1080p, 720p, or 480p).
        """
        if audio_tracks is None:
            try:
                info = cls.probe_video(video_path)
                audio_tracks = info.get('audio_tracks', [])
            except Exception:
                pass

        if audio_tracks is None:
            if has_audio:
                audio_tracks = [{
                    'index': 0,
                    'language': 'und',
                    'title': 'Audio Track 1',
                    'codec': 'aac'
                }]
            else:
                audio_tracks = []

        streams_dir = os.path.join(target_dir, 'streams')
        if os.path.exists(streams_dir):
            shutil.rmtree(streams_dir)
        os.makedirs(streams_dir, exist_ok=True)
        
        num_streams = 1 + len(audio_tracks) if audio_tracks else 1
        for i in range(num_streams):
            os.makedirs(os.path.join(streams_dir, f'stream_{i}'), exist_ok=True)

        active_profiles = [{'name': profile_name, 'w': target_w, 'h': target_h, 'b_v': target_bv, 'b_a': target_ba}]
        has_gpu = cls.detect_gpu_support()

        # Build GPU command (CUDA decoding + NVENC encoding)
        gpu_cmd = []
        if has_gpu:
            gpu_cmd = ['ffmpeg', '-y', '-hwaccel', 'cuda', '-i', video_path, '-progress', '-']
            gpu_vf = [f"scale=-2:{target_h}"]
            gpu_cmd += ['-vf', ",".join(gpu_vf)]
            gpu_cmd += ['-map', '0:v:0', '-c:v', 'h264_nvenc', '-preset', 'fast', '-b:v', target_bv]
            gpu_cmd += ['-maxrate:v', f"{int(target_bv.replace('k', '')) * 1.1:.0f}k"]
            gpu_cmd += ['-bufsize:v', f"{int(target_bv.replace('k', '')) * 1.5:.0f}k"]
            
            gpu_var_stream_map_parts = []
            if audio_tracks:
                gpu_var_stream_map_parts.append("v:0,agroup:audios")
                for idx, track in enumerate(audio_tracks):
                    gpu_cmd += ['-map', f'0:a:{idx}', f'-c:a:{idx}', 'aac', f'-b:a:{idx}', target_ba]
                    lang = track.get('language', 'und')
                    title = track.get('title', f"Audio_{idx + 1}").replace(" ", "_")
                    gpu_var_stream_map_parts.append(f"a:{idx},agroup:audios,language:{lang},name:{title}")
            else:
                gpu_var_stream_map_parts.append("v:0")
                
            gpu_var_stream_map = " ".join(gpu_var_stream_map_parts)
            
            gpu_cmd += [
                '-f', 'hls',
                '-hls_time', '6',
                '-hls_playlist_type', 'event',
                '-master_pl_name', 'master.m3u8',
                '-var_stream_map', gpu_var_stream_map,
                '-hls_segment_filename', os.path.join(streams_dir, 'stream_%v', 'data%03d.ts'),
                os.path.join(streams_dir, 'stream_%v', 'playlist.m3u8')
            ]

        # Build CPU command (fallback or standard)
        cpu_cmd = ['ffmpeg', '-y', '-i', video_path, '-progress', '-']
        cpu_vf = [f"scale=-2:{target_h}"]
        cpu_cmd += ['-vf', ",".join(cpu_vf)]
        cpu_cmd += ['-map', '0:v:0', '-c:v', 'libx264', '-preset', 'veryfast', '-b:v', target_bv]
        cpu_cmd += ['-maxrate:v', f"{int(target_bv.replace('k', '')) * 1.1:.0f}k"]
        cpu_cmd += ['-bufsize:v', f"{int(target_bv.replace('k', '')) * 1.5:.0f}k"]
        
        cpu_var_stream_map_parts = []
        if audio_tracks:
            cpu_var_stream_map_parts.append("v:0,agroup:audios")
            for idx, track in enumerate(audio_tracks):
                cpu_cmd += ['-map', f'0:a:{idx}', f'-c:a:{idx}', 'aac', f'-b:a:{idx}', target_ba]
                lang = track.get('language', 'und')
                title = track.get('title', f"Audio_{idx + 1}").replace(" ", "_")
                cpu_var_stream_map_parts.append(f"a:{idx},agroup:audios,language:{lang},name:{title}")
        else:
            cpu_var_stream_map_parts.append("v:0")
            
        cpu_var_stream_map = " ".join(cpu_var_stream_map_parts)
        
        cpu_cmd += [
            '-f', 'hls',
            '-hls_time', '6',
            '-hls_playlist_type', 'event',
            '-master_pl_name', 'master.m3u8',
            '-var_stream_map', cpu_var_stream_map,
            '-hls_segment_filename', os.path.join(streams_dir, 'stream_%v', 'data%03d.ts'),
            os.path.join(streams_dir, 'stream_%v', 'playlist.m3u8')
        ]

        # Run with GPU first, fallback to CPU on any failure
        if has_gpu:
            try:
                logger.info(f"Attempting GPU/CUDA accelerated HLS transcoding for {profile_name}...")
                cls._execute_ffmpeg_command(gpu_cmd, duration, progress_callback)
            except Exception as gpu_err:
                logger.warning(f"GPU transcoding failed: {gpu_err}. Falling back to CPU...")
                if os.path.exists(streams_dir):
                    shutil.rmtree(streams_dir)
                os.makedirs(streams_dir, exist_ok=True)
                for i in range(num_streams):
                    os.makedirs(os.path.join(streams_dir, f'stream_{i}'), exist_ok=True)
                cls._execute_ffmpeg_command(cpu_cmd, duration, progress_callback)
        else:
            logger.info(f"GPU/CUDA acceleration not available. Running CPU transcoding for {profile_name}...")
            cls._execute_ffmpeg_command(cpu_cmd, duration, progress_callback)

        with open(os.path.join(streams_dir, 'metadata.json'), 'w') as f:
            json.dump({'streams': active_profiles}, f, indent=2)
            
        return active_profiles

    @classmethod
    def transcode_480p(
        cls,
        video_path: str,
        target_dir: str,
        duration: float,
        has_audio: bool,
        progress_callback: Optional[Callable[[float], None]] = None,
        audio_tracks: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """Transcodes a video file to 480p quality."""
        return cls._transcode_to_hls_profile(
            video_path=video_path,
            target_dir=target_dir,
            target_w=854,
            target_h=480,
            target_bv='1000k',
            target_ba='96k',
            profile_name='480p',
            duration=duration,
            has_audio=has_audio,
            progress_callback=progress_callback,
            audio_tracks=audio_tracks
        )

    @classmethod
    def transcode_720p(
        cls,
        video_path: str,
        target_dir: str,
        duration: float,
        has_audio: bool,
        progress_callback: Optional[Callable[[float], None]] = None,
        audio_tracks: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """Transcodes a video file to 720p quality."""
        return cls._transcode_to_hls_profile(
            video_path=video_path,
            target_dir=target_dir,
            target_w=1280,
            target_h=720,
            target_bv='2500k',
            target_ba='128k',
            profile_name='720p',
            duration=duration,
            has_audio=has_audio,
            progress_callback=progress_callback,
            audio_tracks=audio_tracks
        )

    @classmethod
    def transcode_1080p(
        cls,
        video_path: str,
        target_dir: str,
        duration: float,
        has_audio: bool,
        progress_callback: Optional[Callable[[float], None]] = None,
        audio_tracks: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """Transcodes a video file to 1080p quality."""
        return cls._transcode_to_hls_profile(
            video_path=video_path,
            target_dir=target_dir,
            target_w=1920,
            target_h=1080,
            target_bv='4500k',
            target_ba='192k',
            profile_name='1080p',
            duration=duration,
            has_audio=has_audio,
            progress_callback=progress_callback,
            audio_tracks=audio_tracks
        )

    @classmethod
    def package_original_hls(
        cls,
        video_path: str,
        target_dir: str,
        duration: float,
        has_audio: bool,
        progress_callback: Optional[Callable[[float], None]] = None,
        audio_tracks: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """Packages the original video stream directly into HLS segments without transcoding (using stream copy)."""
        if audio_tracks is None:
            try:
                info = cls.probe_video(video_path)
                audio_tracks = info.get('audio_tracks', [])
            except Exception:
                pass

        if audio_tracks is None:
            if has_audio:
                audio_tracks = [{
                    'index': 0,
                    'language': 'und',
                    'title': 'Audio Track 1',
                    'codec': 'copy'
                }]
            else:
                audio_tracks = []

        streams_dir = os.path.join(target_dir, 'streams')
        if os.path.exists(streams_dir):
            shutil.rmtree(streams_dir)
        os.makedirs(streams_dir, exist_ok=True)
        
        num_streams = 1 + len(audio_tracks) if audio_tracks else 1
        for i in range(num_streams):
            os.makedirs(os.path.join(streams_dir, f'stream_{i}'), exist_ok=True)

        active_profiles = [{'name': 'original', 'w': 'original', 'h': 'original', 'b_v': 'original', 'b_a': 'original'}]

        cmd = ['ffmpeg', '-y', '-i', video_path, '-progress', '-']
        cmd += ['-map', '0:v:0', '-c:v', 'copy']
        
        var_stream_map_parts = []
        if audio_tracks:
            var_stream_map_parts.append("v:0,agroup:audios")
            for idx, track in enumerate(audio_tracks):
                cmd += ['-map', f'0:a:{idx}', f'-c:a:{idx}', 'copy']
                lang = track.get('language', 'und')
                title = track.get('title', f"Audio_{idx + 1}").replace(" ", "_")
                var_stream_map_parts.append(f"a:{idx},agroup:audios,language:{lang},name:{title}")
        else:
            var_stream_map_parts.append("v:0")
            
        var_stream_map = " ".join(var_stream_map_parts)
        
        cmd += [
            '-f', 'hls',
            '-hls_time', '4',
            '-hls_playlist_type', 'vod',
            '-start_number', '0',
            '-hls_list_size', '0',
            '-master_pl_name', 'master.m3u8',
            '-var_stream_map', var_stream_map,
            '-hls_segment_filename', os.path.join(streams_dir, 'stream_%v', 'segment_%05d.ts'),
            os.path.join(streams_dir, 'stream_%v', 'playlist.m3u8')
        ]

        logger.info(f"Running fast stream-copy HLS packaging: {' '.join(cmd)}")
        cls._execute_ffmpeg_command(cmd, duration, progress_callback)

        with open(os.path.join(streams_dir, 'metadata.json'), 'w') as f:
            json.dump({'streams': active_profiles}, f, indent=2)
            
        return active_profiles
