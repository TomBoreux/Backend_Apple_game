from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import TemplateView

urlpatterns = [
    path(
        "",
        TemplateView.as_view(template_name="gameapi/game_overview.html"),
        name="game_overview",
    ),
    path(
        "about/",
        TemplateView.as_view(template_name="gameapi/game_overview.html"),
        name="game_about",
    ),
    path(
        "privacy/",
        TemplateView.as_view(template_name="gameapi/privacy_policy.html"),
        name="privacy_policy",
    ),
    path(
        "privacy-policy/",
        TemplateView.as_view(template_name="gameapi/privacy_policy.html"),
        name="privacy_policy_en",
    ),
    path(
        "account-deletion/",
        TemplateView.as_view(template_name="gameapi/account_deletion.html"),
        name="account_deletion",
    ),
    path(
        "delete-account/",
        TemplateView.as_view(template_name="gameapi/account_deletion.html"),
        name="delete_account",
    ),
    path('admin/', admin.site.urls),
    path('api/', include('gameapi.urls')),  
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
