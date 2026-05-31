from django.contrib import admin
from .models import Setting, Video, VideoClip

@admin.register(Setting)
class SettingAdmin(admin.ModelAdmin):
    list_display = ('key', 'value')
    search_fields = ('key', 'value')

@admin.register(Video)
class VideoAdmin(admin.ModelAdmin):
    list_display = ('title', 'status', 'hls_status', 'preview_clip_status', 'preview_status', 'sprite_status', 'progress', 'created_at')
    list_filter = ('status', 'hls_status', 'preview_clip_status', 'preview_status', 'sprite_status', 'transcode_target')
    search_fields = ('title', 'original_path', 'slug')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(VideoClip)
class VideoClipAdmin(admin.ModelAdmin):
    list_display = ('name', 'video', 'start_time', 'end_time', 'category', 'created_at')
    list_filter = ('category', 'created_at')
    search_fields = ('name', 'category', 'video__title')
    readonly_fields = ('created_at',)
