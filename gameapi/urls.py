from django.urls import path
from .views import (
    user_api,
    medecin_api,
    seed_api,
    rapport_medecin_api,
    rapport_complet_api
)

urlpatterns = [
    # USER
    path('user/', user_api),
    path('user/<int:id>/', user_api),

    # MEDECIN
    path('medecin/', medecin_api),
    path('medecin/<int:id>/', medecin_api),

    # SEED LEVEL
    path('seed/', seed_api),
    path('seed/<int:id>/', seed_api),

    # RAPPORT MEDECIN
    path('rapport-medecin/', rapport_medecin_api),
    path('rapport-medecin/<int:id>/', rapport_medecin_api),

    # RAPPORT COMPLET
    path('rapport-complet/', rapport_complet_api),
    path('rapport-complet/<int:id>/', rapport_complet_api),
]