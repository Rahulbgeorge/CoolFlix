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
from django.conf.urls.static import static
from api.views import serve_streamable_file

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')),
    path('media/streamable/<path:relative_path>', serve_streamable_file, name='serve_streamable_file'),
]

if settings.DEBUG:
    # Use normal media serve for fallback items if any, but streamable is intercepted above
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

