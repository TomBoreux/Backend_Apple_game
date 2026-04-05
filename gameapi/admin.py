from django.contrib import admin
from .models import User, SeedLevel, RapportMedecin, RapportComplet, Medecin

admin.site.register(User)
admin.site.register(SeedLevel)
admin.site.register(RapportMedecin)
admin.site.register(RapportComplet)
admin.site.register(Medecin)
