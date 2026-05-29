from django.urls import path
from . import views

urlpatterns = [
    path('config', views.config_api, name='config_api'),
    path('scan', views.scan_api, name='scan_api'),
    path('videos', views.videos_list_api, name='videos_list_api'),
    path('videos/<int:video_id>', views.video_detail_api, name='video_detail_api'),
    path('videos/<int:video_id>/retry', views.video_retry_api, name='video_retry_api'),
    path('parse-url', views.parse_url_api, name='parse_url_api'),
    path('download-magnet', views.download_magnet_api, name='download_magnet_api'),
    path('download-status', views.download_status_api, name='download_status_api'),
    path('delete-torrent', views.delete_torrent_api, name='delete_torrent_api'),
]
