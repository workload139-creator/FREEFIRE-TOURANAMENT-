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
        existing_count = Tournament.objects.count()
        response = self.client.get(reverse("admin:tournaments_tournament_add"))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Tournament.objects.count(), existing_count)

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
        Tournament.objects.filter(status=Tournament.Status.LIVE).update(status=Tournament.Status.UPCOMING)
        tournament = self.make_tournament("Ready BR Round")
        response = self.client.post(
            reverse("admin:tournaments_tournament_change", args=[tournament.pk]),
            {"status": Tournament.Status.LIVE, "_save": "Save"},
            follow=True,
        )

        tournament.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(tournament.status, Tournament.Status.LIVE)

    def test_central_live_monitor_lists_live_and_waiting_tournaments(self):
        Tournament.objects.filter(status=Tournament.Status.LIVE).update(status=Tournament.Status.UPCOMING)
        live = self.make_tournament("Central Monitor LIVE", status=Tournament.Status.LIVE)
        waiting = self.make_tournament("Central Monitor Waiting")
        response = self.client.get(reverse("tournaments:admin_live_monitor"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, live.title)
        self.assertContains(response, waiting.title)
        self.assertContains(response, "Set Room ID / Password &amp; LIVE")
        self.assertContains(response, "Registration Open")

    def test_finishing_live_event_does_not_auto_start_next_full_event(self):
        Tournament.objects.filter(status=Tournament.Status.LIVE).update(status=Tournament.Status.UPCOMING)
        live = self.make_tournament("Current Live Event", status=Tournament.Status.LIVE)
        waiting = self.make_tournament("Next Full Waiting Event")
        Registration.objects.create(
            tournament=waiting,
            player=self.player,
            free_fire_uid="1234567890",
            status=Registration.Status.CONFIRMED,
            payment_verified=True,
        )
        response = self.client.post(
            reverse("tournaments:admin_finish_tournament", args=[live.pk]),
            follow=True,
        )
        live.refresh_from_db()
        waiting.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(live.status, Tournament.Status.COMPLETED)
        self.assertEqual(waiting.status, Tournament.Status.UPCOMING)

    def test_tournament_live_monitor_renders_status_and_first_prize_controls(self):
        tournament = self.make_tournament("Monitor BR Round")
        response = self.client.get(
            reverse("tournaments:admin_tournament_dashboard", args=[tournament.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Live Monitor Controls")
        self.assertContains(response, "First Place Prize")
        self.assertContains(response, "Edit Status")

    def test_live_monitor_can_finish_tournament_and_release_slot(self):
        Tournament.objects.filter(status=Tournament.Status.LIVE).update(status=Tournament.Status.UPCOMING)
        tournament = self.make_tournament("Finished BR Round", status=Tournament.Status.LIVE)
        response = self.client.post(
            reverse("tournaments:admin_finish_tournament", args=[tournament.pk]),
            follow=True,
        )

        tournament.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(tournament.status, Tournament.Status.COMPLETED)

    def test_live_monitor_cannot_finish_upcoming_tournament(self):
        tournament = self.make_tournament("Upcoming BR Round")
        response = self.client.post(
            reverse("tournaments:admin_finish_tournament", args=[tournament.pk]),
            follow=True,
        )

        tournament.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(tournament.status, Tournament.Status.UPCOMING)

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
