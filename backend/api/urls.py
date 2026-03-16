from django.urls import path
from .views import CvExtractView, health

urlpatterns = [
    path("health/", health, name="health"),
    path("cv/extract/", CvExtractView.as_view(), name="cv-extract"),
]