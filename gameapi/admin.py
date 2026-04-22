from django.contrib import admin
from .models import (
    User,
    SeedLevel,
    DoctorReport,
    FullReport,
    Doctor,
    GameApiTokenSession,
)

admin.site.register(User)
admin.site.register(SeedLevel)
admin.site.register(DoctorReport)
admin.site.register(FullReport)
admin.site.register(Doctor)
admin.site.register(GameApiTokenSession)
