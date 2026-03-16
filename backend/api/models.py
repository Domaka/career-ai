from django.db import models


class CvExtract(models.Model):
	profile_id = models.PositiveIntegerField(db_index=True)
	raw_text = models.TextField()
	clean_text = models.TextField()
	structured_json = models.JSONField(default=dict)
	derived_metrics = models.JSONField(default=dict)
	page_count = models.PositiveIntegerField(null=True, blank=True)
	career_level_estimate = models.CharField(max_length=20, default="unknown")
	confidence_score = models.PositiveIntegerField(default=0)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-created_at"]

	def __str__(self) -> str:
		return f"CvExtract(profile_id={self.profile_id}, created_at={self.created_at:%Y-%m-%d})"
