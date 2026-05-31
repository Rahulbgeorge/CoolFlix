from django.db import models

class Setting(models.Model):
    key = models.CharField(max_length=255, unique=True)
    value = models.TextField()

    def __str__(self):
        return f"{self.key}: {self.value}"

class Video(models.Model):
    STATUS_CHOICES = [
        ('not_required', 'Not Required'),
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    title = models.CharField(max_length=255)
    original_path = models.CharField(max_length=1024, unique=True)
    slug = models.SlugField(max_length=255, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    transcode_target = models.CharField(
        max_length=50,
        default='original',
        choices=[
            ('original', 'Original (Streamable As Is)'),
            ('1080p', '1080p Full HD'),
            ('720p', '720p HD'),
            ('480p', '480p SD')
        ]
    )
    hls_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    sprite_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    preview_clip_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    preview_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='not_required')
    has_custom_thumbnail = models.BooleanField(default=False)
    progress = models.FloatField(default=0.0)
    error_message = models.TextField(blank=True, null=True)
    duration = models.FloatField(default=0.0)
    width = models.IntegerField(default=0)
    height = models.IntegerField(default=0)
    
    # New parsed metadata fields
    cleaned_title = models.CharField(max_length=255, default="", blank=True)
    release_year = models.IntegerField(null=True, blank=True)
    languages = models.JSONField(default=list, blank=True)
    resolution = models.CharField(max_length=50, default="", blank=True, null=True)
    quality = models.CharField(max_length=100, default="", blank=True, null=True)
    codec = models.CharField(max_length=50, default="", blank=True, null=True)
    season = models.CharField(max_length=50, default="", blank=True, null=True)
    episode = models.CharField(max_length=50, default="", blank=True, null=True)
    size = models.CharField(max_length=50, default="", blank=True, null=True)
    subtitles = models.BooleanField(default=False)
    is_series = models.BooleanField(default=False)
    hls_required = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} ({self.status})"

class VideoClip(models.Model):
    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name='clips')
    name = models.CharField(max_length=255)
    start_time = models.FloatField()
    end_time = models.FloatField()
    category = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.start_time}s - {self.end_time}s)"

