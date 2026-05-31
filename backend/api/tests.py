from django.test import TestCase, Client
from django.urls import reverse
from .models import Video, VideoClip
import json

class VideoClipAPITests(TestCase):
    def setUp(self):
        self.client = Client()
        self.video = Video.objects.create(
            title="Test Movie",
            original_path="/tmp/test_movie.mp4",
            slug="test-movie",
            status="completed"
        )
        self.clip = VideoClip.objects.create(
            video=self.video,
            name="Intro Scene",
            start_time=10.5,
            end_time=30.0,
            category="Intro"
        )

    def test_get_clips_and_categories(self):
        url = reverse('video_clips_api', args=[self.video.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn('clips', data)
        self.assertIn('categories', data)
        self.assertEqual(len(data['clips']), 1)
        self.assertEqual(data['clips'][0]['name'], "Intro Scene")
        self.assertEqual(data['categories'], ["Intro"])

    def test_create_clip_success(self):
        url = reverse('video_clips_api', args=[self.video.id])
        post_data = {
            'name': 'Action Sequence',
            'category': 'Action',
            'start_time': 45.0,
            'end_time': 90.5
        }
        response = self.client.post(
            url,
            data=json.dumps(post_data),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertEqual(data['clip']['name'], 'Action Sequence')
        self.assertEqual(data['clip']['category'], 'Action')
        self.assertEqual(VideoClip.objects.filter(video=self.video).count(), 2)

    def test_create_clip_validation_errors(self):
        url = reverse('video_clips_api', args=[self.video.id])
        
        # Test empty name
        response = self.client.post(
            url,
            data=json.dumps({'name': '', 'category': 'Test', 'start_time': 10, 'end_time': 20}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        
        # Test negative start time
        response = self.client.post(
            url,
            data=json.dumps({'name': 'T', 'category': 'Test', 'start_time': -1, 'end_time': 20}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)

        # Test end_time <= start_time
        response = self.client.post(
            url,
            data=json.dumps({'name': 'T', 'category': 'Test', 'start_time': 15, 'end_time': 15}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)

    def test_delete_clip_success(self):
        url = reverse('delete_clip_api', args=[self.clip.id])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(VideoClip.objects.filter(id=self.clip.id).count(), 0)

class DownloaderAPITests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_parse_url_api_direct_magnet(self):
        url = reverse('parse_url_api')
        magnet_link = "magnet:?xt=urn:btih:1a907709efe79c39cd778ca2c07f544b0028456d&dn=Captain.America.Civil.War.2016.1080p"
        post_data = {'url': magnet_link}
        response = self.client.post(
            url,
            data=json.dumps(post_data),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertEqual(data['page_title'], "Direct Magnet Link")
        self.assertEqual(len(data['magnets']), 1)
        self.assertEqual(data['magnets'][0]['magnet_link'], magnet_link)
        self.assertEqual(data['magnets'][0]['resolution'], "1080p")
        self.assertEqual(data['magnets'][0]['title'], "Captain America Civil War (2016) [1080P]")
