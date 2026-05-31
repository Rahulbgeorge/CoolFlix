import os
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
from api.models import Video, Setting

class RunTranscoderCommandTests(TestCase):
    @patch('fcntl.flock')
    @patch('api.transcoder.VideoProcessor.process_hls_only')
    @patch('api.transcoder.VideoProcessor.process_sprite_only')
    @patch('api.transcoder.VideoProcessor.process_preview_only')
    @patch('api.transcoder.VideoProcessor.process_preview_clip_only')
    def test_run_transcoder_priority_flow(self, mock_preview_clip, mock_preview, mock_sprite, mock_hls, mock_flock):
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

        # Mock Preview Clip side effect: complete preview clip stage
        def complete_preview_clip(vid_id):
            video = Video.objects.get(id=vid_id)
            video.preview_clip_status = 'completed'
            video.save()
        mock_preview_clip.side_effect = complete_preview_clip

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
        # 1. Preview clips should be processed for both videos
        self.assertEqual(mock_preview_clip.call_count, 2)
        mock_preview_clip.assert_any_call(v1.id)
        mock_preview_clip.assert_any_call(v2.id)

        # 2. Sprite sheet should be generated next
        self.assertEqual(mock_sprite.call_count, 2)
        mock_sprite.assert_any_call(v1.id)
        mock_sprite.assert_any_call(v2.id)

        # 3. Previews generated
        self.assertEqual(mock_preview.call_count, 2)
        mock_preview.assert_any_call(v1.id)
        mock_preview.assert_any_call(v2.id)

        # 4. HLS processed
        self.assertEqual(mock_hls.call_count, 2)
        mock_hls.assert_any_call(v1.id)
        mock_hls.assert_any_call(v2.id)

    @patch('fcntl.flock')
    @patch('api.transcoder.VideoProcessor.process_hls_only')
    @patch('api.transcoder.VideoProcessor.process_sprite_only')
    @patch('api.transcoder.VideoProcessor.process_preview_only')
    @patch('api.transcoder.VideoProcessor.process_preview_clip_only')
    def test_run_transcoder_hls_skipped_by_default(self, mock_preview_clip, mock_preview, mock_sprite, mock_hls, mock_flock):
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

        # Mock Preview Clip: complete preview clip stage
        def complete_preview_clip(vid_id):
            video = Video.objects.get(id=vid_id)
            video.preview_clip_status = 'completed'
            video.save()
        mock_preview_clip.side_effect = complete_preview_clip

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
        self.assertEqual(mock_preview_clip.call_count, 1)
        self.assertEqual(mock_sprite.call_count, 1)
        self.assertEqual(mock_preview.call_count, 1)
        # HLS is skipped, so mock_hls must not be called
        self.assertEqual(mock_hls.call_count, 0)

        # Retrieve and check DB values
        v.refresh_from_db()
        self.assertEqual(v.status, 'completed')
        self.assertEqual(v.hls_status, 'skipped')
        self.assertEqual(v.progress, 100.0)


from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

class VideoThumbnailAPITests(TestCase):
    def setUp(self):
        self.video = Video.objects.create(
            title="Test Thumbnail Video",
            original_path="/path/test_thumb.mp4",
            slug="test-thumb-video",
            status="completed",
            duration=100.0
        )
        
    @patch('api.infrastructure.transcoder.FFmpegTranscoder.generate_thumbnail')
    def test_upload_custom_thumbnail(self, mock_generate):
        # Create a mock image file
        image_file = SimpleUploadedFile(
            "test.jpg", 
            b"file_content", 
            content_type="image/jpeg"
        )
        
        # Call the endpoint
        url = reverse('video_thumbnail_api', args=[self.video.id])
        response = self.client.post(url, {'file': image_file})
        
        self.assertEqual(response.status_code, 200)
        self.video.refresh_from_db()
        self.assertTrue(self.video.has_custom_thumbnail)
        
    @patch('api.infrastructure.transcoder.FFmpegTranscoder.generate_thumbnail')
    def test_delete_custom_thumbnail(self, mock_generate):
        self.video.has_custom_thumbnail = True
        self.video.save()
        
        # Call delete
        url = reverse('video_thumbnail_api', args=[self.video.id])
        response = self.client.delete(url)
        
        self.assertEqual(response.status_code, 200)
        self.video.refresh_from_db()
        self.assertFalse(self.video.has_custom_thumbnail)
        mock_generate.assert_called_once()


class VideoUploadAPITests(TestCase):
    def setUp(self):
        # Configure source location setting in test db
        Setting.objects.update_or_create(key='source_loc', defaults={'value': '/tmp/test_source_loc'})
        os.makedirs('/tmp/test_source_loc', exist_ok=True)

    def tearDown(self):
        # Clean up test directories
        import shutil
        if os.path.exists('/tmp/test_source_loc'):
            try:
                shutil.rmtree('/tmp/test_source_loc')
            except Exception:
                pass

    @patch('api.views.FileNameCleaner.clean')
    @patch('api.views.os.rename')
    def test_upload_video_success(self, mock_rename, mock_clean):
        # Mock filename cleaner response
        mock_clean_res = MagicMock()
        mock_clean_res.cleaned_name = "Cleaned Test Video"
        mock_clean_res.new_filepath = "/tmp/test_source_loc/Cleaned_Test_Video.mp4"
        mock_clean_res.year = 2024
        mock_clean_res.languages = ["en"]
        mock_clean_res.resolution = "1080p"
        mock_clean_res.quality = "WEBDL"
        mock_clean_res.codec = "h264"
        mock_clean_res.season = None
        mock_clean_res.episode = None
        mock_clean_res.size = "1.2GB"
        mock_clean_res.subtitles = False
        mock_clean_res.is_series = False
        mock_clean.return_value = mock_clean_res

        # Create a mock video file
        video_file = SimpleUploadedFile(
            "uploaded_movie.mp4", 
            b"fake_video_stream_content", 
            content_type="video/mp4"
        )

        url = reverse('upload_video_api')
        response = self.client.post(url, {'file': video_file})

        self.assertEqual(response.status_code, 200)
        resp_data = response.json()
        self.assertTrue(resp_data['success'])
        
        # Check that Video record was created
        self.assertTrue(Video.objects.filter(title="Cleaned Test Video").exists())


class NetworkInfoAPITests(TestCase):
    def test_network_info(self):
        url = reverse('network_info_api')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('client_ip', data)
        self.assertIn('server_local_ip', data)
        self.assertIn('same_network', data)




