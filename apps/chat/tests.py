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



class PartyRoomQuizSecurityTests(TestCase):
    def setUp(self):
        from django.utils import timezone
        from datetime import timedelta
        from .party_models import PartyRoom, PartyRoomMembership, PartyRoomMessage

        self.owner = User.objects.create_user(username="party_owner", password="test-password-12345")
        self.guest = User.objects.create_user(username="party_guest", password="test-password-12345")
        self.room = PartyRoom.objects.create(
            host=self.owner, title="Private test room", visibility=PartyRoom.Visibility.PRIVATE,
            passcode="secret-code", max_members=12,
        )
        PartyRoomMembership.objects.create(room=self.room, user=self.owner)
        PartyRoomMessage.objects.create(room=self.room, sender=self.owner, body="private-room-secret-message")
        self.client.force_login(self.guest)

    def test_private_room_does_not_expose_chat_to_non_member(self):
        response = self.client.get(reverse("chat:party_room", args=[self.room.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "private-room-secret-message")

    def test_private_room_wrong_passcode_does_not_join(self):
        response = self.client.post(
            reverse("chat:party_room", args=[self.room.pk]),
            {"action": "join", "passcode": "wrong-code"},
        )
        self.assertEqual(response.status_code, 302)
        from .party_models import PartyRoomMembership
        self.assertFalse(PartyRoomMembership.objects.filter(room=self.room, user=self.guest).exists())

    def test_only_current_turn_player_can_submit_answer(self):
        from datetime import timedelta
        from django.utils import timezone
        from .party_models import PartyRoom, PartyRoomMembership, PartyRoomGameAnswer

        self.room.visibility = PartyRoom.Visibility.PUBLIC
        self.room.game_status = "live"
        self.room.game_round = 1
        self.room.game_question = "What does BR mean?"
        self.room.game_answer = "br"
        self.room.current_turn_player = self.owner
        self.room.game_deadline = timezone.now() + timedelta(seconds=30)
        self.room.save()
        PartyRoomMembership.objects.create(room=self.room, user=self.guest)
        response = self.client.post(
            reverse("chat:party_game_answer", args=[self.room.pk]),
            {"answer": "battle royale"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(PartyRoomGameAnswer.objects.filter(room=self.room, player=self.guest).exists())
