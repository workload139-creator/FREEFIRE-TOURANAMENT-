from django.conf import settings
from django.db import models
from django.db.models import Q


class PartyRoom(models.Model):
    class Visibility(models.TextChoices):
        PUBLIC = "public", "Public"
        PRIVATE = "private", "Private"

    host = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="hosted_party_rooms")
    title = models.CharField(max_length=70)
    description = models.CharField(max_length=240, blank=True)
    theme = models.CharField(max_length=16, default="violet", choices=[("violet", "Violet"), ("gold", "Gold"), ("ocean", "Ocean"), ("fire", "Fire")])
    visibility = models.CharField(max_length=10, choices=Visibility.choices, default=Visibility.PUBLIC)
    passcode = models.CharField(max_length=24, blank=True)
    max_members = models.PositiveSmallIntegerField(default=12)
    is_open = models.BooleanField(default=True)
    game_status = models.CharField(max_length=12, choices=[("lobby", "Lobby"), ("live", "Live"), ("completed", "Completed")], default="lobby", db_index=True)
    current_round = models.PositiveSmallIntegerField(default=0)
    auto_start = models.BooleanField(default=False, help_text="Start the quiz automatically when the room reaches 12 members.")
    game_phase = models.CharField(max_length=12, choices=[("lobby", "Lobby"), ("question", "Question"), ("decision", "Decision"), ("completed", "Completed")], default="lobby", db_index=True)
    phase_deadline = models.DateTimeField(null=True, blank=True)
    decision_index = models.PositiveSmallIntegerField(default=0)
    game_winner_awarded = models.BooleanField(default=False)
    winner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="party_quiz_wins")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at",)

    def __str__(self):
        return self.title

    @property
    def member_count(self):
        return self.memberships.count()


class PartyRoomMembership(models.Model):
    room = models.ForeignKey(PartyRoom, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="party_room_memberships")
    joined_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    is_muted = models.BooleanField(default=False)
    is_eliminated = models.BooleanField(default=False, db_index=True)
    eliminated_round = models.PositiveSmallIntegerField(null=True, blank=True)
    elimination_reason = models.CharField(max_length=24, blank=True)
    current_answer = models.CharField(max_length=1, blank=True)
    answered_at = models.DateTimeField(null=True, blank=True)
    score = models.PositiveSmallIntegerField(default=0)
    decision_done = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("room", "user"), name="chat_party_room_unique_member")]
        ordering = ("joined_at",)


class PartyRoomMessage(models.Model):
    room = models.ForeignKey(PartyRoom, on_delete=models.CASCADE, related_name="room_messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="party_room_messages")
    body = models.CharField(max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("created_at", "pk")


class PartyRoomGift(models.Model):
    room = models.ForeignKey(PartyRoom, on_delete=models.CASCADE, related_name="room_gifts")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="party_room_gifts_sent")
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="party_room_gifts_received")
    gift_code = models.CharField(max_length=20)
    currency = models.CharField(max_length=12, choices=[("diamonds", "Diamonds"), ("coins", "Coins"), ("fan_tokens", "Fan Tokens")])
    quantity = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)


class CommunityTournament(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Registration open"
        LIVE = "live", "Live"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    host = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="community_tournaments")
    title = models.CharField(max_length=90)
    game_mode = models.CharField(max_length=20, choices=[("BR", "Battle Royale"), ("CS_1V1", "CS 1v1"), ("CS_2V2", "CS 2v2"), ("CS_3V3", "CS 3v3"), ("CS_4V4", "CS 4v4")])
    description = models.CharField(max_length=500, blank=True)
    starts_at = models.DateTimeField()
    max_players = models.PositiveSmallIntegerField(default=12)
    entry_note = models.CharField(max_length=120, blank=True, help_text="Use this to describe free entry or rules. This community feature does not collect entry fees.")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("starts_at", "-created_at")

    def __str__(self):
        return self.title


class CommunityTournamentEntry(models.Model):
    tournament = models.ForeignKey(CommunityTournament, on_delete=models.CASCADE, related_name="entries")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="community_tournament_entries")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("tournament", "user"), name="chat_community_tournament_unique_entry")]
        ordering = ("created_at",)
