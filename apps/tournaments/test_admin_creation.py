from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Tournament


class TournamentAdminCreationTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin_user = user_model.objects.create_superuser(
            username="tournament-admin-test",
            email="admin@example.test",
            password="test-only-password-12345",
        )
        self.client.force_login(self.admin_user)

    def test_add_form_uses_easy_datetime_input_and_upcoming_default(self):
        response = self.client.get(reverse("admin:tournaments_tournament_add"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'type="datetime-local"')
        self.assertContains(response, 'value="upcoming" selected')

    def test_admin_can_create_tournament_that_appears_on_public_list(self):
        start_time = timezone.localtime(
            timezone.now() + timedelta(days=1)
        ).strftime("%Y-%m-%dT%H:%M")

        response = self.client.post(
            reverse("admin:tournaments_tournament_add"),
            {
                "title": "Admin Created Test Tournament",
                "mode": Tournament.Mode.BR,
                "vs_format": "",
                "description": "Created through Django admin test.",
                "entry_fee": "10.00",
                "prize_pool": "100.00",
                "max_players": "49",
                "start_time": start_time,
                "status": Tournament.Status.UPCOMING,
                "room_id": "",
                "room_password": "",
                "registrations-TOTAL_FORMS": "0",
                "registrations-INITIAL_FORMS": "0",
                "registrations-MIN_NUM_FORMS": "0",
                "registrations-MAX_NUM_FORMS": "1000",
                "kill_submissions-TOTAL_FORMS": "0",
                "kill_submissions-INITIAL_FORMS": "0",
                "kill_submissions-MIN_NUM_FORMS": "0",
                "kill_submissions-MAX_NUM_FORMS": "1000",
                "_save": "Save",
            },
            follow=True,
        )

        self.assertEqual(
            Tournament.objects.filter(
                title="Admin Created Test Tournament",
                status=Tournament.Status.UPCOMING,
            ).count(),
            1,
            msg=response.content.decode("utf-8", errors="replace")[:5000],
        )

        public_response = self.client.get(reverse("tournaments:list"))
        self.assertContains(public_response, "Admin Created Test Tournament")
