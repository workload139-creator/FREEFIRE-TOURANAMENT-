import json
import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Registration, Tournament, TournamentLiveMessage, TournamentLiveSession


class LiveMonitorPrivateMessageTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser(
            username="live-message-admin",
            email="live-message-admin@example.test",
            password="test-only-password-12345",
        )
        self.player = User.objects.create_user(
            username="live-message-player",
            password="test-only-password-12345",
        )
        self.tournament = Tournament.objects.create(
            title="Live Message Test",
            mode=Tournament.Mode.BR,
            br_format=Tournament.BRFormat.SOLO,
            start_time=timezone.now() + timedelta(minutes=5),
            status=Tournament.Status.LIVE,
        )
        self.registration = Registration.objects.create(
            tournament=self.tournament,
            player=self.player,
            free_fire_uid="123456789",
            payment_verified=True,
            status=Registration.Status.READY,
        )
        self.session = TournamentLiveSession.objects.create(
            tournament=self.tournament,
            registration=self.registration,
            session_uuid=uuid.uuid4(),
            room_name="ffarena-test-player-room",
            participant_identity="ffarena-test-player",
        )

    def test_staff_can_send_private_message_and_player_can_read_it(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("tournaments:admin_live_message", args=[self.registration.pk]),
            data=json.dumps({"message": "Please show your lobby UID clearly."}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(TournamentLiveMessage.objects.count(), 1)

        self.client.force_login(self.player)
        response = self.client.get(
            reverse("tournaments:player_live_messages", args=[self.registration.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["messages"][0]["message"], "Please show your lobby UID clearly.")
        self.assertIsNotNone(TournamentLiveMessage.objects.get().read_at)

    def test_non_staff_cannot_send_player_live_message(self):
        self.client.force_login(self.player)
        response = self.client.post(
            reverse("tournaments:admin_live_message", args=[self.registration.pk]),
            data=json.dumps({"message": "hello"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(TournamentLiveMessage.objects.count(), 0)

    def test_player_cannot_read_another_players_live_messages(self):
        other = self.client
        other.force_login(self.admin)
        TournamentLiveMessage.objects.create(
            registration=self.registration, sender=self.admin, body="Private instruction"
        )
        # A staff account is not the player who owns this registration.
        response = other.get(
            reverse("tournaments:player_live_messages", args=[self.registration.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_admin_message_length_is_limited(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("tournaments:admin_live_message", args=[self.registration.pk]),
            data=json.dumps({"message": "x" * 501}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(TournamentLiveMessage.objects.count(), 0)
