# Tournament Admin now controls existing rounds; round creation is disabled.
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

    def make_tournament(self, title, status=Tournament.Status.UPCOMING):
        return Tournament.objects.create(
            title=title,
            mode=Tournament.Mode.BR,
            br_format=Tournament.BRFormat.SOLO,
            entry_fee="10.00",
            prize_pool="100.00",
            max_players=49,
            start_time=timezone.now() + timedelta(days=1),
            status=status,
            room_id="ROOM123",
            room_password="PASS123",
        )

    def test_admin_cannot_create_new_tournament(self):
        response = self.client.get(reverse("admin:tournaments_tournament_add"))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Tournament.objects.count(), 0)

    def test_existing_tournament_edit_exposes_only_status_control(self):
        tournament = self.make_tournament("Existing BR Round")
        response = self.client.get(
            reverse("admin:tournaments_tournament_change", args=[tournament.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tournament Control")
        self.assertNotContains(response, 'name="title"')
        self.assertNotContains(response, 'name="entry_fee"')
        self.assertNotContains(response, 'name="prize_pool"')
        self.assertContains(response, 'name="status"')
        self.assertContains(response, 'value="live"')
        self.assertContains(response, 'value="cancelled"')
        self.assertNotContains(response, 'value="completed"')

    def test_admin_can_start_existing_tournament_when_no_other_is_live(self):
        tournament = self.make_tournament("Ready BR Round")
        response = self.client.post(
            reverse("admin:tournaments_tournament_change", args=[tournament.pk]),
            {"status": Tournament.Status.LIVE, "_save": "Save"},
            follow=True,
        )

        tournament.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(tournament.status, Tournament.Status.LIVE)

    def test_admin_cannot_start_second_live_tournament(self):
        Tournament.objects.create(
            title="Already Live",
            mode=Tournament.Mode.BR,
            br_format=Tournament.BRFormat.SOLO,
            entry_fee="10.00",
            prize_pool="100.00",
            max_players=49,
            start_time=timezone.now() + timedelta(days=1),
            status=Tournament.Status.LIVE,
            room_id="ROOM-LIVE",
            room_password="PASS-LIVE",
        )
        waiting = self.make_tournament("Waiting BR Round")
        response = self.client.post(
            reverse("admin:tournaments_tournament_change", args=[waiting.pk]),
            {"status": Tournament.Status.LIVE, "_save": "Save"},
            follow=True,
        )

        waiting.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(waiting.status, Tournament.Status.UPCOMING)
