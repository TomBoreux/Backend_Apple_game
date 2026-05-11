from django.db import models
from django.utils import timezone


class Doctor(models.Model):
    last_name = models.CharField(max_length=100)
    first_name = models.CharField(max_length=100)
    token = models.CharField(max_length=255, unique=True)
    email = models.EmailField(max_length=100, unique=True)

    def __str__(self):
        return f"{self.last_name} {self.first_name}"


class User(models.Model):
    token = models.CharField(max_length=255)
    uuid = models.CharField(max_length=255, null=True, blank=True)
    birth_year = models.IntegerField(null=True, blank=True)
    doctors = models.ManyToManyField("Doctor", related_name="users", blank=True)

    class Meta:
        unique_together = ("token", "uuid")

    def __str__(self):
        return f"{self.id} | token={self.token} | uuid={self.uuid}"


class SeedLevel(models.Model):
    name = models.CharField(max_length=100)
    file = models.FileField(upload_to="seeds/")

    def __str__(self):
        return self.name or str(self.file)



class FullReport(models.Model):
    session_id = models.CharField(max_length=255)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="full_reports")
    file = models.FileField(upload_to="reports/full/")
    date = models.DateTimeField(auto_now_add=True)
    app_version = models.CharField(max_length=32, blank=True, db_index=True)
    app_version_code = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    level_generation_version = models.CharField(max_length=64, blank=True, db_index=True)
    client_platform = models.CharField(max_length=32, blank=True)
    seed_levels = models.ManyToManyField("SeedLevel", related_name="full_reports", blank=True)

    class Meta:
        unique_together = ("user", "session_id")

    def __str__(self):
        return f"RapportComplet {self.user.id} _ {self.id}"


class GameApiTokenSession(models.Model):
    device_uuid = models.CharField(max_length=255, blank=True, default="")
    user_agent = models.CharField(max_length=255, blank=True, default="")
    refresh_token_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["expires_at"]),
            models.Index(fields=["revoked_at"]),
        ]

    def is_active(self):
        return self.revoked_at is None and self.expires_at > timezone.now()

    def revoke(self):
        if self.revoked_at is None:
            self.revoked_at = timezone.now()
            self.save(update_fields=["revoked_at", "last_used_at"])

    def touch(self):
        self.save(update_fields=["last_used_at"])

    def __str__(self):
        return f"GameApiTokenSession {self.id} active={self.is_active()}"
