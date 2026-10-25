from unittest.mock import patch

from django.db import OperationalError
from django.test import TestCase
from django.urls import reverse


class HealthCheckTests(TestCase):
    def test_health_check_reports_database_connection(self):
        response = self.client.get(reverse("health_check"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"status": "ok", "database": "ok"},
        )

    @patch("apps.core.views.connection.ensure_connection")
    def test_health_check_hides_database_error_details(self, ensure_connection):
        ensure_connection.side_effect = OperationalError("private database details")

        response = self.client.get(reverse("health_check"))

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {"status": "unhealthy", "database": "unavailable"},
        )
        self.assertNotContains(response, "private database details", status_code=503)
