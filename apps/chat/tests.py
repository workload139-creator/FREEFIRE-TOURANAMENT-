from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.social.models import FriendRequest
from .models import Conversation, Message

User = get_user_model()


class PrivateChatTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(username="alice", password="test-password-12345")
        self.bob = User.objects.create_user(username="bob", password="test-password-12345")
        self.client.force_login(self.alice)

    def test_non_friend_cannot_open_chat(self):
        response = self.client.get(reverse("chat:open", args=[self.bob.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Conversation.objects.exists())

    def test_accepted_friends_can_exchange_messages(self):
        FriendRequest.objects.create(
            requester=self.alice, recipient=self.bob, status=FriendRequest.Status.ACCEPTED
        )
        response = self.client.get(reverse("chat:open", args=[self.bob.pk]))
        self.assertEqual(response.status_code, 302)
        conversation = Conversation.objects.get()
        self.client.post(reverse("chat:conversation", args=[conversation.pk]), {"body": "Hello friend!"})
        self.assertEqual(Message.objects.get().body, "Hello friend!")
        self.client.force_login(self.bob)
        response = self.client.get(reverse("chat:conversation", args=[conversation.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(Message.objects.get().read_at)

    def test_unrelated_user_cannot_read_conversation(self):
        FriendRequest.objects.create(
            requester=self.alice, recipient=self.bob, status=FriendRequest.Status.ACCEPTED
        )
        conversation = Conversation.objects.create(user_one=self.alice, user_two=self.bob)
        charlie = User.objects.create_user(username="charlie", password="test-password-12345")
        self.client.force_login(charlie)
        response = self.client.get(reverse("chat:conversation", args=[conversation.pk]))
        self.assertEqual(response.status_code, 302)
