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



class PartyRoomCreateJoinTests(TestCase):
    def setUp(self):
        from .party_models import PartyRoom, PartyRoomMembership
        self.PartyRoom = PartyRoom
        self.PartyRoomMembership = PartyRoomMembership
        self.host = User.objects.create_user(username="party_host", password="test-password-12345")
        self.player = User.objects.create_user(username="party_player", password="test-password-12345")
        self.client.force_login(self.host)

    def test_create_room_redirects_and_room_page_renders(self):
        response = self.client.post(reverse("chat:party_create_room"), {"title": "Test Voice Party"})
        self.assertEqual(response.status_code, 302)
        room = self.PartyRoom.objects.get(title="Test Voice Party", host=self.host)
        self.assertTrue(self.PartyRoomMembership.objects.filter(room=room, user=self.host).exists())
        response = self.client.get(reverse("chat:party_room", args=[room.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Voice Party")
        self.assertContains(response, "FF Arena Quiz")

    def test_player_can_join_public_room_and_reopen_page(self):
        room = self.PartyRoom.objects.create(host=self.host, title="Joinable Voice Party")
        self.PartyRoomMembership.objects.create(room=room, user=self.host)
        self.client.force_login(self.player)
        response = self.client.post(reverse("chat:party_room", args=[room.pk]), {"action": "join"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.PartyRoomMembership.objects.filter(room=room, user=self.player).exists())
        response = self.client.get(reverse("chat:party_room", args=[room.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Joinable Voice Party")

    def test_live_room_rejects_new_player_without_server_error(self):
        room = self.PartyRoom.objects.create(host=self.host, title="Live Voice Party", game_status="live", game_phase="question")
        self.PartyRoomMembership.objects.create(room=room, user=self.host)
        self.client.force_login(self.player)
        response = self.client.post(reverse("chat:party_room", args=[room.pk]), {"action": "join"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(self.PartyRoomMembership.objects.filter(room=room, user=self.player).exists())

    def test_party_room_has_separate_speaker_sound_control(self):
        room = self.PartyRoom.objects.create(host=self.host, title="Sound Control Party")
        self.PartyRoomMembership.objects.create(room=room, user=self.host)
        response = self.client.get(reverse("chat:party_room", args=[room.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="partyVoiceSound"')
        self.assertContains(response, "Speaker sound off. Aapki microphone setting alag hai.")

    def test_party_home_explains_fixed_twelve_player_start(self):
        response = self.client.get(reverse("chat:party"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "poore 12 players room mein hone par hi game start hoga.")
        self.assertNotContains(response, "kam se kam 2 players hon")


class PartyQuizAutoDrawRestartTests(TestCase):
    def setUp(self):
        from datetime import timedelta
        from django.utils import timezone
        from .party_models import PartyRoom, PartyRoomMembership

        self.host = User.objects.create_user(username="quiz_host", password="test-password-12345")
        self.player = User.objects.create_user(username="quiz_player", password="test-password-12345")
        self.room = PartyRoom.objects.create(
            host=self.host, title="Auto Draw Quiz", game_status="live",
            game_phase="question", current_round=1,
            phase_deadline=timezone.now() + timedelta(seconds=30),
        )
        self.host_member = PartyRoomMembership.objects.create(room=self.room, user=self.host)
        self.player_member = PartyRoomMembership.objects.create(room=self.room, user=self.player)

    def test_all_wrong_answers_draw_then_auto_restart_with_current_roster(self):
        from datetime import timedelta
        from django.utils import timezone

        self.room.phase_deadline = timezone.now() - timedelta(seconds=1)
        self.room.save(update_fields=["phase_deadline"])
        self.client.force_login(self.host)
        state = self.client.get(reverse("chat:party_game_state", args=[self.room.pk]))
        self.assertEqual(state.status_code, 200)

        self.room.refresh_from_db()
        self.assertEqual(self.room.game_phase, "draw")
        self.assertEqual(self.room.game_status, "live")
        self.assertIsNone(self.room.winner_id)
        self.assertFalse(self.room.game_winner_awarded)

        self.room.phase_deadline = timezone.now() - timedelta(seconds=1)
        self.room.save(update_fields=["phase_deadline"])
        self.client.force_login(self.host)
        state = self.client.get(reverse("chat:party_game_state", args=[self.room.pk]))
        self.assertEqual(state.status_code, 200)
        self.assertEqual(state.json()["phase"], "question")
        self.assertEqual(state.json()["round"], 1)
        self.host_member.refresh_from_db()
        self.player_member.refresh_from_db()
        self.assertFalse(self.host_member.is_eliminated)
        self.assertFalse(self.player_member.is_eliminated)
        self.assertEqual(self.host_member.score, 0)
        self.assertEqual(self.player_member.score, 0)

    def test_ajax_start_sends_same_live_question_to_every_joined_player(self):
        from .party_game import QUESTIONS
        start_url = reverse("chat:party_room", args=[self.room.pk])
        self.room.game_status = "lobby"
        self.room.game_phase = "lobby"
        self.room.save(update_fields=["game_status", "game_phase"])
        self.client.force_login(self.host)
        started = self.client.post(
            start_url, {"action": "start_game"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(started.status_code, 200)
        self.assertTrue(started.json()["ok"])
        self.assertEqual(started.json()["players"], 2)
        state_url = reverse("chat:party_game_state", args=[self.room.pk])
        host_state = self.client.get(state_url).json()
        self.client.force_login(self.player)
        player_state = self.client.get(state_url).json()
        self.assertEqual(host_state["phase"], "question")
        self.assertEqual(player_state["phase"], "question")
        self.assertEqual(host_state["question"], player_state["question"])
        self.assertEqual(host_state["choices"], player_state["choices"])
        self.assertTrue(host_state["question"])
        self.assertTrue(player_state["question"])
        self.assertGreaterEqual(host_state["seconds_left"], 40)
        self.assertGreaterEqual(player_state["seconds_left"], 40)


class PartyQuizWinnerAndQuestionTests(TestCase):
    def setUp(self):
        from datetime import timedelta
        from django.utils import timezone
        from .party_models import PartyRoom, PartyRoomMembership
        self.host = User.objects.create_user(username="quiz_last_host", password="test-password-12345")
        self.player = User.objects.create_user(username="quiz_last_player", password="test-password-12345")
        self.room = PartyRoom.objects.create(
            host=self.host, title="Last Player Wins", game_status="live",
            game_phase="question", current_round=1,
            phase_deadline=timezone.now() + timedelta(seconds=30),
            game_question_ids=[1, 2, 3],
        )
        PartyRoomMembership.objects.create(room=self.room, user=self.host)
        PartyRoomMembership.objects.create(room=self.room, user=self.player)

    def test_last_survivor_wins_and_gets_five_fan_tokens_once(self):
        from apps.social.models import PlayerShopWallet
        from .party_game import QUESTIONS
        answer_url = reverse("chat:party_game_answer", args=[self.room.pk])
        self.client.force_login(self.host)
        correct = QUESTIONS[1]["correct"]
        self.assertEqual(self.client.post(answer_url, {"answer": correct}).status_code, 200)
        self.client.force_login(self.player)
        self.assertEqual(self.client.post(answer_url, {"answer": "SKIP"}).status_code, 200)
        self.room.refresh_from_db()
        self.assertEqual(self.room.game_phase, "completed")
        self.assertEqual(self.room.winner_id, self.host.pk)
        self.assertTrue(self.room.game_winner_awarded)
        wallet = PlayerShopWallet.objects.get(user=self.host)
        self.assertEqual(wallet.fan_tokens, 5)
        self.client.get(reverse("chat:party_game_state", args=[self.room.pk]))
        wallet.refresh_from_db()
        self.assertEqual(wallet.fan_tokens, 5)

    def test_each_new_game_selects_three_distinct_questions(self):
        from django.db import transaction
        from .party_game import begin_quiz, QUESTIONS
        with transaction.atomic():
            locked = type(self.room).objects.select_for_update().get(pk=self.room.pk)
            self.assertTrue(begin_quiz(locked))
        self.room.refresh_from_db()
        self.assertEqual(len(self.room.game_question_ids), 3)
        self.assertEqual(len(set(self.room.game_question_ids)), 3)
        self.assertTrue(set(self.room.game_question_ids).issubset(set(QUESTIONS)))
        self.assertTrue(set(self.room.game_question_ids).isdisjoint({1, 2, 3}))


class PartyQuizManualDrawRestartTests(TestCase):
    def setUp(self):
        from .party_models import PartyRoom, PartyRoomMembership
        self.host = User.objects.create_user(username="draw_restart_host", password="test-password-12345")
        self.player = User.objects.create_user(username="draw_restart_player", password="test-password-12345")
        self.room = PartyRoom.objects.create(
            host=self.host, title="Manual Draw Restart",
            game_status="completed", game_phase="completed", current_round=1,
        )
        self.host_member = PartyRoomMembership.objects.create(room=self.room, user=self.host, is_eliminated=True)
        self.player_member = PartyRoomMembership.objects.create(room=self.room, user=self.player, is_eliminated=True)

    def test_host_can_restart_after_completed_match_with_winner_or_draw(self):
        from .party_game import QUESTIONS
        self.client.force_login(self.host)
        response = self.client.post(reverse("chat:party_game_restart_draw", args=[self.room.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.room.refresh_from_db()
        self.assertEqual(self.room.game_phase, "question")
        self.assertEqual(self.room.current_round, 1)
        self.assertEqual(len(self.room.game_question_ids), 3)
        self.host_member.refresh_from_db()
        self.player_member.refresh_from_db()
        self.assertFalse(self.host_member.is_eliminated)
        self.assertFalse(self.player_member.is_eliminated)
        self.assertFalse(self.host_member.current_answer)
        self.assertFalse(self.player_member.current_answer)

    def test_non_host_cannot_restart_completed_game(self):
        self.client.force_login(self.player)
        response = self.client.post(reverse("chat:party_game_restart_draw", args=[self.room.pk]))
        self.assertEqual(response.status_code, 403)
        self.room.refresh_from_db()
        self.assertEqual(self.room.game_phase, "draw")
