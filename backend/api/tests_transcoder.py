import json
from unittest.mock import patch, MagicMock
from django.test import SimpleTestCase
from .infrastructure.transcoder import FFmpegTranscoder

class FFmpegTranscoderTests(SimpleTestCase):
    @patch('subprocess.run')
    def test_probe_video(self, mock_run):
        # Mock successful ffprobe output
        mock_result = MagicMock()
        mock_result.stdout = json.dumps({
            'format': {'duration': '120.5'},
            'streams': [
                {'codec_type': 'video', 'width': 1920, 'height': 1080, 'duration': '120.5'},
                {'codec_type': 'audio'}
            ]
        })
        mock_run.return_value = mock_result
        
        info = FFmpegTranscoder.probe_video("dummy_path.mp4")
        self.assertEqual(info['duration'], 120.5)
        self.assertEqual(info['width'], 1920)
        self.assertEqual(info['height'], 1080)
        self.assertTrue(info['has_audio'])
        
        # Verify ffprobe arguments
        args, kwargs = mock_run.call_args
        self.assertIn('ffprobe', args[0])
        self.assertIn('dummy_path.mp4', args[0])

    @patch('subprocess.run')
    def test_generate_thumbnail(self, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result
        
        thumbnail = FFmpegTranscoder.generate_thumbnail("video.mp4", "/tmp", 60.0)
        self.assertTrue(thumbnail.endswith("thumbnail.jpg"))
        
        args, kwargs = mock_run.call_args
        self.assertIn('ffmpeg', args[0])
        self.assertIn('60.0', args[0])
        self.assertIn('video.mp4', args[0])

    @patch('subprocess.run')
    def test_detect_gpu_support_success(self, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result
        self.assertTrue(FFmpegTranscoder.detect_gpu_support())

    @patch('subprocess.run')
    def test_detect_gpu_support_failure(self, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_run.return_value = mock_result
        self.assertFalse(FFmpegTranscoder.detect_gpu_support())

    @patch('subprocess.Popen')
    def test_transcode_hls_copy(self, mock_popen):
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.stdout = ["out_time_us=60000000\n"]
        mock_popen.return_value = mock_process

        profiles = FFmpegTranscoder.transcode_hls(
            video_path="video.mp4",
            target_dir="/tmp",
            width=1920,
            height=1080,
            duration=120.0,
            has_audio=True,
            target_quality='original',
            video_codec='h264',
            audio_codec='aac'
        )

        self.assertEqual(profiles[0]['b_v'], 'original')
        args, kwargs = mock_popen.call_args
        cmd_str = " ".join(args[0])
        self.assertIn('-c:v copy', cmd_str)
        self.assertIn('-c:a copy', cmd_str)

    @patch('subprocess.Popen')
    @patch('api.infrastructure.transcoder.FFmpegTranscoder.detect_gpu_support')
    def test_transcode_hls_transcode_gpu(self, mock_detect_gpu, mock_popen):
        mock_detect_gpu.return_value = True
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.stdout = ["out_time_us=60000000\n"]
        mock_popen.return_value = mock_process

        profiles = FFmpegTranscoder.transcode_hls(
            video_path="video.mp4",
            target_dir="/tmp",
            width=1920,
            height=1080,
            duration=120.0,
            has_audio=True,
            target_quality='720p',
            video_codec='h264',
            audio_codec='mp3' # incompatible audio, forcing transcode
        )

        self.assertEqual(profiles[0]['w'], 1280)
        args, kwargs = mock_popen.call_args
        cmd_str = " ".join(args[0])
        self.assertIn('-hwaccel cuda', cmd_str)
        self.assertIn('-c:v h264_nvenc', cmd_str)

    @patch('subprocess.Popen')
    @patch('api.infrastructure.transcoder.FFmpegTranscoder.detect_gpu_support')
    def test_transcode_hls_transcode_gpu_fallback(self, mock_detect_gpu, mock_popen):
        mock_detect_gpu.return_value = True
        
        # First call to Popen (GPU command) fails, second call (CPU fallback) succeeds
        mock_gpu_process = MagicMock()
        mock_gpu_process.returncode = 1
        mock_gpu_process.stdout = ["error\n"]
        
        mock_cpu_process = MagicMock()
        mock_cpu_process.returncode = 0
        mock_cpu_process.stdout = ["out_time_us=60000000\n"]
        
        mock_popen.side_effect = [mock_gpu_process, mock_cpu_process]

        profiles = FFmpegTranscoder.transcode_hls(
            video_path="video.mp4",
            target_dir="/tmp",
            width=1920,
            height=1080,
            duration=120.0,
            has_audio=True,
            target_quality='720p',
            video_codec='h264',
            audio_codec='mp3'
        )

        self.assertEqual(mock_popen.call_count, 2)
        # Verify the second call was the CPU fallback (libx264)
        second_call_args = mock_popen.call_args_list[1][0][0]
        cmd_str = " ".join(second_call_args)
        self.assertIn('-c:v libx264', cmd_str)
        self.assertNotIn('-hwaccel cuda', cmd_str)


from django.test import TestCase
from django.core.management import call_command
from api.models import Video

class RunTranscoderCommandTests(TestCase):
    @patch('api.transcoder.VideoProcessor.process_video_pipeline')
    def test_run_transcoder_command(self, mock_process):
        # Create a pending video
        video1 = Video.objects.create(
            title="Test Video 1",
            original_path="/path/to/video1.mp4",
            slug="test-video-1",
            status="pending"
        )
        # Create a completed video
        Video.objects.create(
            title="Test Video 2",
            original_path="/path/to/video2.mp4",
            slug="test-video-2",
            status="completed"
        )
        
        # Run the command
        call_command('run_transcoder')
        
        # Verify that process_video_pipeline was called on the pending video only
        mock_process.assert_called_once_with(video1.id)
