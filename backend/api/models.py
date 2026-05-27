from django.db import models

class Setting(models.Model):
    key = models.CharField(max_length=255, unique=True)
    value = models.TextField()

    def __str__(self):
        return f"{self.key}: {self.value}"

class Video(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    title = models.CharField(max_length=255)
    original_path = models.CharField(max_length=1024, unique=True)
    slug = models.SlugField(max_length=255, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    progress = models.FloatField(default=0.0)
    error_message = models.TextField(blank=True, null=True)
    duration = models.FloatField(default=0.0)
    width = models.IntegerField(default=0)
    height = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} ({self.status})"
