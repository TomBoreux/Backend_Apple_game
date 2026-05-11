from rest_framework import serializers

from .models import (
    User,
    Doctor,
    SeedLevel,
    FullReport,
)


class DoctorSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Doctor
        fields = ("id", "last_name", "first_name", "token", "email")


class UserSerializer(serializers.ModelSerializer):
    doctors = DoctorSummarySerializer(many=True, read_only=True)
    latest_doctor_id = serializers.SerializerMethodField()
    latest_doctor_token = serializers.SerializerMethodField()
    doctor_key = serializers.SerializerMethodField()

    def _get_latest_doctor(self, obj):
        return obj.doctors.order_by("-id").first()

    def get_latest_doctor_id(self, obj):
        doctor = self._get_latest_doctor(obj)
        return doctor.id if doctor else None

    def get_latest_doctor_token(self, obj):
        doctor = self._get_latest_doctor(obj)
        return doctor.token if doctor else ""

    def get_doctor_key(self, obj):
        doctor = self._get_latest_doctor(obj)
        return doctor.token if doctor else ""

    class Meta:
        model = User
        fields = (
            "id",
            "token",
            "uuid",
            "birth_year",
            "doctors",
            "latest_doctor_id",
            "latest_doctor_token",
            "doctor_key",
        )


class DoctorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Doctor
        fields = ("id", "last_name", "first_name", "token", "email")


class SeedLevelSerializer(serializers.ModelSerializer):
    class Meta:
        model = SeedLevel
        fields = ("id", "name", "file")


class FullReportSerializer(serializers.ModelSerializer):
    file = serializers.FileField()
    seed_levels = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=SeedLevel.objects.all(),
        required=False,
    )

    class Meta:
        model = FullReport
        fields = (
            "id",
            "user",
            "session_id",
            "file",
            "date",
            "seed_levels",
            "app_version",
            "app_version_code",
            "level_generation_version",
            "client_platform",
        )
        validators = []
