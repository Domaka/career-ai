from django.contrib import admin

from .models import CvAnalysis, CvExtract


@admin.register(CvExtract)
class CvExtractAdmin(admin.ModelAdmin):
	list_display = (
		"id",
		"profile_id",
		"career_level_estimate",
		"confidence_score",
		"created_at",
	)
	list_filter = ("career_level_estimate", "created_at")
	search_fields = ("profile_id",)


@admin.register(CvAnalysis)
class CvAnalysisAdmin(admin.ModelAdmin):
	list_display = (
		"id",
		"profile_id",
		"source",
		"created_at",
	)
	list_filter = ("source", "created_at")
	search_fields = ("profile_id",)

# Register your models here.
