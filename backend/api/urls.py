from django.urls import path
from . import views

urlpatterns = [
    path('config', views.config_api, name='config_api'),
    path('scan', views.scan_api, name='scan_api'),
    path('videos', views.videos_list_api, name='videos_list_api'),
    path('videos/<int:video_id>', views.video_detail_api, name='video_detail_api'),
    path('videos/<int:video_id>/retry', views.video_retry_api, name='video_retry_api'),
    # Video streaming is handled directly by Nginx via range queries (206 Partial Content)
    # dynamically initiated through Django returning X-Accel-Redirect headers.
    path('parse-url', views.parse_url_api, name='parse_url_api'),
    path('download-magnet', views.download_magnet_api, name='download_magnet_api'),
    path('download-status', views.download_status_api, name='download_status_api'),
    path('delete-torrent', views.delete_torrent_api, name='delete_torrent_api'),
    path('videos/<int:video_id>/clips', views.video_clips_api, name='video_clips_api'),
    path('videos/clips/<int:clip_id>', views.delete_clip_api, name='delete_clip_api'),
    path('videos/<int:video_id>/thumbnail', views.video_thumbnail_api, name='video_thumbnail_api'),
    path('videos/upload', views.upload_video_api, name='upload_video_api'),
    path('network-info', views.network_info_api, name='network_info_api'),
]
