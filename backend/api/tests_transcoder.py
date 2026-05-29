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

    @patch('subprocess.Popen')
    def test_transcode_hls(self, mock_popen):
        # Mock running Popen
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.stdout = [
            "frame=100\n",
            "out_time_us=60000000\n",  # 60 seconds progress
            "speed=2x\n"
        ]
        mock_popen.return_value = mock_process
        
        progress_calls = []
        def progress_cb(percent):
            progress_calls.append(percent)
            
        profiles = FFmpegTranscoder.transcode_hls(
            video_path="video.mp4",
            target_dir="/tmp",
            width=1920,
            height=1080,
            duration=120.0,
            has_audio=True,
            progress_callback=progress_cb
        )
        
        # 60s / 120s = 50.0% progress
        self.assertIn(50.0, progress_calls)
        self.assertTrue(len(profiles) > 0)
