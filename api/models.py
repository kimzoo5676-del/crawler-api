from django.db import models

# Create your models here.
class JobPosting(models.Model):
    company = models.CharField(max_length=100)
    title = models.CharField(max_length=200)
    url = models.URLField(unique=True)
    location = models.CharField(max_length=100, blank=True)
    deadline = models.DateField(null=True, blank=True)
    source = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"[{self.company}] {self.title}"