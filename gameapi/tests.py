from django.test import TestCase
from rest_framework.test import APIRequestFactory

from .views import get_client_ip


class GetClientIpTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    def test_prefers_x_forwarded_for_first_ip(self):
        request = self.factory.get(
            "/api/user/",
            HTTP_X_FORWARDED_FOR="203.0.113.10, 198.51.100.2",
            REMOTE_ADDR="127.0.0.1",
        )

        self.assertEqual(get_client_ip(request), "203.0.113.10")

    def test_falls_back_to_x_real_ip(self):
        request = self.factory.get(
            "/api/user/",
            HTTP_X_REAL_IP="198.51.100.7",
            REMOTE_ADDR="127.0.0.1",
        )

        self.assertEqual(get_client_ip(request), "198.51.100.7")

    def test_falls_back_to_remote_addr(self):
        request = self.factory.get("/api/user/", REMOTE_ADDR="192.0.2.25")

        self.assertEqual(get_client_ip(request), "192.0.2.25")
