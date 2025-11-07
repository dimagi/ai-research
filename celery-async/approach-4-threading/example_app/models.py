"""
Django models for tracking API calls and tasks.
"""
from django.db import models


class APILog(models.Model):
    """Log of API HTTP requests."""
    url = models.URLField(max_length=500)
    status_code = models.IntegerField()
    response_time = models.FloatField(help_text="Response time in seconds")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'API Log'
        verbose_name_plural = 'API Logs'

    def __str__(self):
        return f"{self.url} - {self.status_code} ({self.response_time}s)"


class Task(models.Model):
    """Record of Celery task execution."""
    name = models.CharField(max_length=200)
    status = models.CharField(max_length=50)
    result = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} - {self.status}"
