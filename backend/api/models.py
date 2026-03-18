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


class CvAnalysis(models.Model):
	SOURCE_CHOICES = (
		("rules", "Rules"),
		("gemini", "Gemini"),
	)

	profile_id = models.PositiveIntegerField(db_index=True)
	cv_extract = models.OneToOneField(CvExtract, on_delete=models.CASCADE, related_name="analysis")
	summary = models.TextField(blank=True, default="")
	strengths = models.JSONField(default=list)
	weaknesses = models.JSONField(default=list)
	talent_gaps = models.JSONField(default=list)
	analysis_json = models.JSONField(default=dict)
	source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default="rules")
	fallback_reason = models.TextField(blank=True, default="")
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-created_at"]

	def __str__(self) -> str:
		return f"CvAnalysis(profile_id={self.profile_id}, source={self.source}, created_at={self.created_at:%Y-%m-%d})"
