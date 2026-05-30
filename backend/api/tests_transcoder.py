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
        self.assertIn('-c:a:0 copy', cmd_str)

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
    @patch('api.transcoder.VideoProcessor.process_hls_only')
    @patch('api.transcoder.VideoProcessor.process_sprite_only')
    @patch('api.transcoder.VideoProcessor.process_preview_only')
    def test_run_transcoder_priority_flow(self, mock_preview, mock_sprite, mock_hls):
        # Create 2 pending videos
        v1 = Video.objects.create(
            title="Video 1",
            original_path="/path/v1.mp4",
            slug="v1",
            status="pending",
            hls_status="pending",
            sprite_status="pending",
            preview_status="pending",
            hls_required=True
        )
        v2 = Video.objects.create(
            title="Video 2",
            original_path="/path/v2.mp4",
            slug="v2",
            status="pending",
            hls_status="pending",
            sprite_status="pending",
            preview_status="pending",
            hls_required=True
        )

        # Mock Sprite side effect: complete Sprite stage
        def complete_sprite(vid_id):
            video = Video.objects.get(id=vid_id)
            video.sprite_status = 'completed'
            video.status = 'processing'
            video.save()
        mock_sprite.side_effect = complete_sprite

        # Mock Preview side effect: complete Preview stage and set overall status to completed (playable)
        def complete_preview(vid_id):
            video = Video.objects.get(id=vid_id)
            video.preview_status = 'completed'
            video.status = 'completed'
            video.save()
        mock_preview.side_effect = complete_preview

        # Mock HLS side effect: complete HLS stage
        def complete_hls(vid_id):
            video = Video.objects.get(id=vid_id)
            video.hls_status = 'completed'
            video.save()
        mock_hls.side_effect = complete_hls

        # Run the transcoder cron command
        call_command('run_transcoder')

        # Assertions:
        # 1. HLS should be processed for both videos first (first priority)
        self.assertEqual(mock_hls.call_count, 2)
        mock_hls.assert_any_call(v1.id)
        mock_hls.assert_any_call(v2.id)

        # 2. Sprite sheet should be generated next
        self.assertEqual(mock_sprite.call_count, 2)
        mock_sprite.assert_any_call(v1.id)
        mock_sprite.assert_any_call(v2.id)

        # 3. Previews generated last
        self.assertEqual(mock_preview.call_count, 2)
        mock_preview.assert_any_call(v1.id)
        mock_preview.assert_any_call(v2.id)

    @patch('api.transcoder.VideoProcessor.process_hls_only')
    @patch('api.transcoder.VideoProcessor.process_sprite_only')
    @patch('api.transcoder.VideoProcessor.process_preview_only')
    def test_run_transcoder_hls_skipped_by_default(self, mock_preview, mock_sprite, mock_hls):
        # Create a pending video with hls_required=False (default)
        v = Video.objects.create(
            title="Video Default",
            original_path="/path/default.mp4",
            slug="default-vid",
            status="pending",
            hls_status="pending",
            sprite_status="pending",
            preview_status="pending",
            hls_required=False
        )

        # Mock Sprite: complete Sprite stage and set progress
        def complete_sprite(vid_id):
            video = Video.objects.get(id=vid_id)
            video.sprite_status = 'completed'
            video.progress = 50.0
            video.save()
        mock_sprite.side_effect = complete_sprite

        # Mock Preview: complete Preview stage, set progress, hls_status='skipped', status='completed'
        def complete_preview(vid_id):
            video = Video.objects.get(id=vid_id)
            video.preview_status = 'completed'
            video.hls_status = 'skipped'
            video.status = 'completed'
            video.progress = 100.0
            video.save()
        mock_preview.side_effect = complete_preview

        # Run the transcoder cron command
        call_command('run_transcoder')

        # Assertions:
        # Sprite sheet and preview generated
        self.assertEqual(mock_sprite.call_count, 1)
        self.assertEqual(mock_preview.call_count, 1)
        # HLS is skipped, so mock_hls must not be called
        self.assertEqual(mock_hls.call_count, 0)

        # Retrieve and check DB values
        v.refresh_from_db()
        self.assertEqual(v.status, 'completed')
        self.assertEqual(v.hls_status, 'skipped')
        self.assertEqual(v.progress, 100.0)

