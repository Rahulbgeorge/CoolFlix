from django.urls import path
from . import views

urlpatterns = [
    path('config', views.config_api, name='config_api'),
    path('scan', views.scan_api, name='scan_api'),
    path('videos', views.videos_list_api, name='videos_list_api'),
    path('videos/<int:video_id>', views.video_detail_api, name='video_detail_api'),
    path('videos/<int:video_id>/retry', views.video_retry_api, name='video_retry_api'),
]
