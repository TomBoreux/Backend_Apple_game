from django.urls import path
from .views import (
    create_game_api_token,
    refresh_game_api_token,
    user_api,
    doctor_api,
    seed_api,
    doctor_report_api,
    full_report_api,
)

urlpatterns = [
    path("auth/token/", create_game_api_token),
    path("auth/refresh/", refresh_game_api_token),
    path("user/", user_api),
    path("user/<int:id>/", user_api),
    path("doctor/", doctor_api),
    path("doctor/<int:id>/", doctor_api),
    path("seed/", seed_api),
    path("seed/<int:id>/", seed_api),
    path("doctor-report/", doctor_report_api),
    path("doctor-report/<int:id>/", doctor_report_api),
    path("full-report/", full_report_api),
    path("full-report/<int:id>/", full_report_api),
]
