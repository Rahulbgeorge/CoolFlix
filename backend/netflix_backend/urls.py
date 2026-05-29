"""
URL configuration for netflix_backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.views.static import serve
from api.views import serve_streamable_file, serve_frontend

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')),
    path('media/streamable/<path:relative_path>', serve_streamable_file, name='serve_streamable_file'),
    # Serve media files including built frontend assets
    path('media/<path:path>', serve, {'document_root': settings.MEDIA_ROOT}),
    # Serve frontend index.html for root path
    path('', serve_frontend, name='frontend_root'),
    # Catch-all to support frontend SPA client routes
    path('<path:path>', serve_frontend, name='frontend_catchall'),
]

