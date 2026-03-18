from django.urls import path
from .views import CvExtractView, LoginView, LogoutView, MeView, RegisterView, health

urlpatterns = [
    path("health/", health, name="health"),
    path("auth/register/", RegisterView.as_view(), name="auth-register"),
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path("auth/me/", MeView.as_view(), name="auth-me"),
    path("cv/extract/", CvExtractView.as_view(), name="cv-extract"),
]