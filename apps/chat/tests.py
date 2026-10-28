from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.social.models import Follow, FriendRequest
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
        Follow.objects.create(follower=self.alice, following=self.bob)
        Follow.objects.create(follower=self.bob, following=self.alice)
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
        Follow.objects.create(follower=self.alice, following=self.bob)
        Follow.objects.create(follower=self.bob, following=self.alice)
        conversation = Conversation.objects.create(user_one=self.alice, user_two=self.bob)
        charlie = User.objects.create_user(username="charlie", password="test-password-12345")
        self.client.force_login(charlie)
        response = self.client.get(reverse("chat:conversation", args=[conversation.pk]))
        self.assertEqual(response.status_code, 302)


class ChatGiftTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(username="gift_sender", password="test-password-12345")
        self.bob = User.objects.create_user(username="gift_receiver", password="test-password-12345")
        Follow.objects.create(follower=self.alice, following=self.bob)
        self.conversation = Conversation.objects.create(user_one=self.alice, user_two=self.bob)
        from apps.social.models import PlayerShopWallet
        self.sender_wallet = PlayerShopWallet.objects.create(user=self.alice, diamonds=10, coins=5, fan_tokens=3)
        self.receiver_wallet = PlayerShopWallet.objects.create(user=self.bob)
        self.client.force_login(self.alice)

    def test_rose_gift_deducts_and_credits_same_currency(self):
        response = self.client.post(reverse("chat:conversation", args=[self.conversation.pk]), {
            "action": "gift", "gift_code": "rose", "currency": "diamonds",
        })
        self.assertEqual(response.status_code, 302)
        self.sender_wallet.refresh_from_db()
        self.receiver_wallet.refresh_from_db()
        self.assertEqual(self.sender_wallet.diamonds, 8)
        self.assertEqual(self.receiver_wallet.diamonds, 2)
        from apps.social.models import CurrencyGift
        self.assertEqual(CurrencyGift.objects.get().quantity, 2)

    def test_trophy_gift_cannot_overdraw_wallet(self):
        self.client.post(reverse("chat:conversation", args=[self.conversation.pk]), {
            "action": "gift", "gift_code": "trophy", "currency": "coins",
        })
        self.sender_wallet.refresh_from_db()
        self.receiver_wallet.refresh_from_db()
        self.assertEqual(self.sender_wallet.coins, 5)
        self.assertEqual(self.receiver_wallet.coins, 0)

    def test_invalid_gift_code_does_not_transfer_currency(self):
        self.client.post(reverse("chat:conversation", args=[self.conversation.pk]), {
            "action": "gift", "gift_code": "not-a-gift", "currency": "diamonds",
        })
        self.sender_wallet.refresh_from_db()
        self.receiver_wallet.refresh_from_db()
        self.assertEqual(self.sender_wallet.diamonds, 10)
        self.assertEqual(self.receiver_wallet.diamonds, 0)
