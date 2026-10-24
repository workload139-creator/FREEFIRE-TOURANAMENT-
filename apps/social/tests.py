from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import FriendRequest, UserBlock

User = get_user_model()


class SocialFlowTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(username="alice", password="test-password-12345")
        self.bob = User.objects.create_user(username="bob", password="test-password-12345")
        self.client.force_login(self.alice)

    def test_player_id_search_finds_user(self):
        response = self.client.get(reverse("social:home"), {"q": f"FF-{self.bob.pk:06d}"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "bob")

    def test_friend_request_can_be_sent_and_accepted(self):
        self.client.post(reverse("social:send_request", args=[self.bob.pk]))
        request_obj = FriendRequest.objects.get(requester=self.alice, recipient=self.bob)
        self.client.force_login(self.bob)
        self.client.post(reverse("social:handle_request", args=[request_obj.pk, "accept"]))
        request_obj.refresh_from_db()
        self.assertEqual(request_obj.status, FriendRequest.Status.ACCEPTED)

    def test_self_friend_request_is_rejected(self):
        self.client.post(reverse("social:send_request", args=[self.alice.pk]))
        self.assertFalse(FriendRequest.objects.filter(requester=self.alice, recipient=self.alice).exists())

    def test_blocked_user_is_not_in_search_results(self):
        UserBlock.objects.create(blocker=self.alice, blocked=self.bob)
        response = self.client.get(reverse("social:home"), {"q": "bob"})
        self.assertEqual(response.context["search_results"], [])
