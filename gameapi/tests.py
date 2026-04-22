from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from .models import (
    GameApiTokenSession,
    Medecin as Doctor,
    RapportComplet as FullReport,
    RapportMedecin as DoctorReport,
    SeedLevel,
    User,
)


class GameApiAuthMixin:
    bootstrap_token = "super-secret"

    def issue_game_tokens(self, uuid="test-device"):
        response = self.client.post(
            "/api/auth/token/",
            {"uuid": uuid},
            format="json",
            HTTP_X_GAME_API_KEY=self.bootstrap_token,
        )
        self.assertEqual(response.status_code, 201)
        return response.data

    def issue_access_token(self, uuid="test-device"):
        return self.issue_game_tokens(uuid)["access_token"]

    def auth_headers(self, access_token=None):
        token = access_token or self.issue_access_token()
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


@override_settings(GAME_API_WRITE_TOKEN="super-secret")
class UserApiAgeTests(GameApiAuthMixin, TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_post_creates_user_with_age(self):
        response = self.client.post(
            "/api/user/",
            {"token": "player", "uuid": "uuid-age-1", "age": 27},
            format="json",
            **self.auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["age"], 27)

        user = User.objects.get(token="player", uuid="uuid-age-1")
        self.assertEqual(user.age, 27)

    def test_post_updates_existing_user_age(self):
        user = User.objects.create(token="player", uuid="uuid-age-2", age=18)

        response = self.client.post(
            "/api/user/",
            {"token": "player", "uuid": "uuid-age-2", "age": 21},
            format="json",
            **self.auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertEqual(user.age, 21)

    def test_post_rejects_non_integer_age(self):
        response = self.client.post(
            "/api/user/",
            {"token": "player", "uuid": "uuid-age-3", "age": "abc"},
            format="json",
            **self.auth_headers(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "age must be an integer")


@override_settings(GAME_API_WRITE_TOKEN="super-secret")
class ApiSecurityTests(GameApiAuthMixin, TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin_user = get_user_model().objects.create_user(
            username="admin",
            password="admin-pass-123",
            is_staff=True,
            is_superuser=True,
        )
        self.user = User.objects.create(token="secured-user", uuid="uuid-secured")
        self.doctor = Doctor.objects.create(
            last_name="House",
            first_name="Gregory",
            token="med-secure",
            email="house-secure@example.com",
        )

    def test_user_get_requires_admin(self):
        response = self.client.get("/api/user/")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["error"], "admin authentication or valid access token required")

    def test_user_get_allows_admin(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.get("/api/user/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)

    def test_doctor_post_requires_admin(self):
        response = self.client.post(
            "/api/doctor/",
            {
                "last_name": "Cuddy",
                "first_name": "Lisa",
                "token": "med-new",
                "email": "cuddy@example.com",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["error"], "admin authentication required")

    def test_doctor_post_allows_admin(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.post(
            "/api/doctor/",
            {
                "last_name": "Cuddy",
                "first_name": "Lisa",
                "token": "med-new",
                "email": "cuddy@example.com",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["token"], "med-new")

    def test_create_token_requires_bootstrap_key(self):
        response = self.client.post("/api/auth/token/", {"uuid": "device-1"}, format="json")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["error"], "valid bootstrap API key required")

    def test_create_token_returns_access_and_refresh_tokens(self):
        response = self.client.post(
            "/api/auth/token/",
            {"uuid": "device-1"},
            format="json",
            HTTP_X_GAME_API_KEY=self.bootstrap_token,
        )

        self.assertEqual(response.status_code, 201)
        self.assertIn("access_token", response.data)
        self.assertIn("refresh_token", response.data)
        self.assertEqual(response.data["token_type"], "Bearer")
        self.assertTrue(GameApiTokenSession.objects.filter(id=response.data["session_id"]).exists())

    def test_refresh_rotates_tokens(self):
        issued = self.issue_game_tokens("device-2")

        response = self.client.post(
            "/api/auth/refresh/",
            {"refresh_token": issued["refresh_token"]},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response.data["access_token"], issued["access_token"])
        self.assertNotEqual(response.data["refresh_token"], issued["refresh_token"])

    def test_refresh_token_cannot_be_reused_after_rotation(self):
        issued = self.issue_game_tokens("device-3")

        first_refresh = self.client.post(
            "/api/auth/refresh/",
            {"refresh_token": issued["refresh_token"]},
            format="json",
        )

        self.assertEqual(first_refresh.status_code, 200)

        second_refresh = self.client.post(
            "/api/auth/refresh/",
            {"refresh_token": issued["refresh_token"]},
            format="json",
        )

        self.assertEqual(second_refresh.status_code, 401)
        self.assertEqual(second_refresh.data["error"], "refresh token is invalid or expired")

    def test_refresh_rejects_revoked_session(self):
        issued = self.issue_game_tokens("device-4")
        session = GameApiTokenSession.objects.get(id=issued["session_id"])
        session.revoked_at = timezone.now()
        session.save(update_fields=["revoked_at"])

        response = self.client.post(
            "/api/auth/refresh/",
            {"refresh_token": issued["refresh_token"]},
            format="json",
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["error"], "refresh token is invalid or expired")

    def test_user_get_by_token_accepts_bearer_access_token(self):
        access_token = self.issue_access_token()
        self.user.age = 72
        self.user.save(update_fields=["age"])
        self.user.doctors.add(self.doctor)

        response = self.client.get(
            "/api/user/?token=secured-user",
            **self.auth_headers(access_token),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["token"], "secured-user")
        self.assertEqual(response.data["age"], 72)
        self.assertEqual(response.data["latest_doctor_token"], "med-secure")
        self.assertEqual(response.data["doctor_key"], "med-secure")
        self.assertEqual(response.data["doctors"][0]["token"], "med-secure")

    def test_user_get_by_token_returns_latest_doctor_by_highest_id(self):
        access_token = self.issue_access_token()
        older_doctor = Doctor.objects.create(
            last_name="Older",
            first_name="Doctor",
            token="med-older",
            email="older@example.com",
        )
        newer_doctor = Doctor.objects.create(
            last_name="Newer",
            first_name="Doctor",
            token="med-newer",
            email="newer@example.com",
        )
        self.user.doctors.add(older_doctor, newer_doctor)

        response = self.client.get(
            "/api/user/?token=secured-user",
            **self.auth_headers(access_token),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["latest_doctor_token"], "med-newer")
        self.assertEqual(response.data["doctor_key"], "med-newer")

    def test_user_get_without_filter_rejects_access_token(self):
        access_token = self.issue_access_token()
        response = self.client.get(
            "/api/user/",
            **self.auth_headers(access_token),
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["error"], "filtered lookup required for access token usage")

    def test_doctor_get_by_token_accepts_bearer_access_token(self):
        access_token = self.issue_access_token()
        response = self.client.get(
            "/api/doctor/?token=med-secure",
            **self.auth_headers(access_token),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["token"], "med-secure")

    def test_user_post_requires_write_token_when_enabled(self):
        response = self.client.post(
            "/api/user/",
            {"token": "player", "uuid": "uuid-locked"},
            format="json",
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["error"], "admin authentication or valid access token required")

    def test_user_post_accepts_bearer_access_token_when_enabled(self):
        access_token = self.issue_access_token()
        response = self.client.post(
            "/api/user/",
            {"token": "player", "uuid": "uuid-locked"},
            format="json",
            **self.auth_headers(access_token),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["token"], "player")


@override_settings(GAME_API_WRITE_TOKEN="super-secret")
class UserApiDoctorTokenTests(GameApiAuthMixin, TestCase):
    def setUp(self):
        self.client = APIClient()
        self.doctor = Doctor.objects.create(
            last_name="House",
            first_name="Gregory",
            token="med-1",
            email="house@example.com",
        )

    def test_post_links_existing_doctor_to_new_user(self):
        response = self.client.post(
            "/api/user/",
            {
                "token": "player-med-1",
                "uuid": "uuid-med-1",
                "doctor_token": "med-1",
            },
            format="json",
            **self.auth_headers(),
        )

        self.assertEqual(response.status_code, 200)

        user = User.objects.get(token="player-med-1", uuid="uuid-med-1")
        self.assertEqual(list(user.doctors.values_list("id", flat=True)), [self.doctor.id])

    def test_post_links_existing_doctor_from_doctor_id(self):
        response = self.client.post(
            "/api/user/",
            {
                "token": "player-med-id",
                "uuid": "uuid-med-id",
                "doctor_id": self.doctor.id,
            },
            format="json",
            **self.auth_headers(),
        )

        self.assertEqual(response.status_code, 200)

        user = User.objects.get(token="player-med-id", uuid="uuid-med-id")
        self.assertEqual(list(user.doctors.values_list("id", flat=True)), [self.doctor.id])

    def test_post_links_existing_doctor_from_doctor_key(self):
        response = self.client.post(
            "/api/user/",
            {
                "token": "player-med-key",
                "uuid": "uuid-med-key",
                "doctor_key": "med-1",
            },
            format="json",
            **self.auth_headers(),
        )

        self.assertEqual(response.status_code, 200)

        user = User.objects.get(token="player-med-key", uuid="uuid-med-key")
        self.assertEqual(list(user.doctors.values_list("id", flat=True)), [self.doctor.id])

    def test_post_links_existing_doctor_to_existing_user_without_changing_patient_logic(self):
        user = User.objects.create(token="player-med-2", uuid="uuid-med-2", age=18)

        response = self.client.post(
            "/api/user/",
            {
                "token": "player-med-2",
                "uuid": "uuid-med-2",
                "age": 21,
                "doctor_token": "med-1",
            },
            format="json",
            **self.auth_headers(),
        )

        self.assertEqual(response.status_code, 200)

        user.refresh_from_db()
        self.assertEqual(user.age, 21)
        self.assertEqual(list(user.doctors.values_list("id", flat=True)), [self.doctor.id])

    def test_post_keeps_same_user_for_same_patient_token_and_links_doctor(self):
        user = User.objects.create(token="player-med-keep", uuid="uuid-old", age=18)

        response = self.client.post(
            "/api/user/",
            {
                "token": "player-med-keep",
                "uuid": "uuid-new",
                "doctor_token": "med-1",
            },
            format="json",
            **self.auth_headers(),
        )

        self.assertEqual(response.status_code, 200)

        user.refresh_from_db()
        self.assertEqual(User.objects.filter(token="player-med-keep").count(), 1)
        self.assertEqual(user.uuid, "uuid-new")
        self.assertEqual(list(user.doctors.values_list("id", flat=True)), [self.doctor.id])

    def test_post_rejects_unknown_doctor_token(self):
        response = self.client.post(
            "/api/user/",
            {
                "token": "player-med-3",
                "uuid": "uuid-med-3",
                "doctor_token": "unknown-med",
            },
            format="json",
            **self.auth_headers(),
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["error"], "doctor token does not exist")
        self.assertFalse(User.objects.filter(token="player-med-3", uuid="uuid-med-3").exists())

    def test_post_rejects_doctor_token_even_if_matching_user_token(self):
        User.objects.create(token="shared-token", uuid="uuid-existing-user")

        response = self.client.post(
            "/api/user/",
            {
                "token": "player-med-4",
                "uuid": "uuid-med-4",
                "doctor_token": "shared-token",
            },
            format="json",
            **self.auth_headers(),
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["error"], "doctor token does not exist")
        self.assertFalse(User.objects.filter(token="player-med-4", uuid="uuid-med-4").exists())


@override_settings(GAME_API_WRITE_TOKEN="super-secret")
class FullReportSessionTests(GameApiAuthMixin, TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create(token="player", uuid="uuid-1")

    def test_post_updates_existing_full_report_for_same_session(self):
        first_file = SimpleUploadedFile(
            "full_report_level_1.txt",
            b"niveau 1",
            content_type="text/plain",
        )
        response = self.client.post(
            "/api/full-report/",
            {"user": self.user.id, "session_id": "session-123", "file": first_file},
            format="multipart",
            **self.auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(FullReport.objects.count(), 1)

        report = FullReport.objects.get()
        first_id = report.id
        self.assertEqual(report.session_id, "session-123")

        second_file = SimpleUploadedFile(
            "full_report_level_2.txt",
            b"niveau 2",
            content_type="text/plain",
        )
        response = self.client.post(
            "/api/full-report/",
            {"user": self.user.id, "session_id": "session-123", "file": second_file},
            format="multipart",
            **self.auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(FullReport.objects.count(), 1)

        report.refresh_from_db()
        self.assertEqual(report.id, first_id)
        self.assertIn("full_report_level_2", report.file.name)


@override_settings(GAME_API_WRITE_TOKEN="super-secret")
class DoctorReportSessionTests(GameApiAuthMixin, TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create(token="doctor-player", uuid="uuid-2")
        self.seed_1 = SeedLevel.objects.create(
            name="niveau-1",
            seed_file=SimpleUploadedFile("seed_1.txt", b"seed 1", content_type="text/plain"),
        )
        self.seed_2 = SeedLevel.objects.create(
            name="niveau-2",
            seed_file=SimpleUploadedFile("seed_2.txt", b"seed 2", content_type="text/plain"),
        )
        self.doctor_1 = Doctor.objects.create(
            last_name="House",
            first_name="Gregory",
            token="med-1",
            email="house@example.com",
        )
        self.doctor_2 = Doctor.objects.create(
            last_name="Cuddy",
            first_name="Lisa",
            token="med-2",
            email="cuddy@example.com",
        )

    def test_post_updates_existing_doctor_report_for_same_session(self):
        first_file = SimpleUploadedFile(
            "doctor_report_level_1.txt",
            b"niveau 1",
            content_type="text/plain",
        )
        response = self.client.post(
            "/api/doctor-report/",
            {
                "user": self.user.id,
                "session_id": "session-doctor-123",
                "seed": self.seed_1.id,
                "file": first_file,
                "doctors": [self.doctor_1.id],
            },
            format="multipart",
            **self.auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(DoctorReport.objects.count(), 1)

        report = DoctorReport.objects.get()
        first_id = report.id
        self.assertEqual(report.session_id, "session-doctor-123")
        self.assertEqual(report.seed_id, self.seed_1.id)
        self.assertEqual(list(report.doctors.values_list("id", flat=True)), [self.doctor_1.id])

        second_file = SimpleUploadedFile(
            "doctor_report_level_2.txt",
            b"niveau 2",
            content_type="text/plain",
        )
        response = self.client.post(
            "/api/doctor-report/",
            {
                "user": self.user.id,
                "session_id": "session-doctor-123",
                "seed": self.seed_2.id,
                "file": second_file,
                "doctors": [self.doctor_2.id],
            },
            format="multipart",
            **self.auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(DoctorReport.objects.count(), 1)

        report.refresh_from_db()
        self.assertEqual(report.id, first_id)
        self.assertEqual(report.seed_id, self.seed_2.id)
        self.assertEqual(list(report.doctors.values_list("id", flat=True)), [self.doctor_2.id])
        self.assertIn("doctor_report_level_2", report.file.name)
