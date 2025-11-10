from django.db import models


class RequestLog(models.Model):
    """Model to log HTTP requests made during task execution"""

    task_id = models.CharField(max_length=255, db_index=True)
    url = models.URLField()
    method = models.CharField(max_length=10, default='GET')
    status_code = models.IntegerField(null=True, blank=True)
    response_time = models.FloatField(help_text="Response time in seconds")
    success = models.BooleanField(default=True)
    error_message = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at', 'task_id']),
        ]

    def __str__(self):
        return f"{self.task_id} - {self.method} {self.url} ({self.status_code})"
