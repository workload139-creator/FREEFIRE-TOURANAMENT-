from datetime import timedelta
from decimal import Decimal

from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.db import transaction
from django.utils import timezone
from django.utils.html import format_html
from django.urls import reverse

from apps.accounts.models import (
    AdminWallet,
    AdminWalletTransaction,
    WalletTransaction,
)
from .constants import PLAYER_CONFIRMATION_TIMEOUT_SECONDS
from .models import KillSubmission, Registration, Tournament, TournamentLedgerEntry, UnlimitedTournament, FreeFanTournament, DiwaliOfferTournament

from .services import cancel_tournament_and_refund
from .kill_services import reward_for_tournament
from .registration_services import assign_teams_for_tournament, tournament_team_size


class TournamentAdminForm(forms.ModelForm):
    """Make tournament creation easier and default new tournaments to public status."""

    start_time = forms.DateTimeField(
        input_formats=[
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
        ],
        widget=forms.DateTimeInput(
            format="%Y-%m-%dT%H:%M",
            attrs={"type": "datetime-local"},
        ),
    )

    class Meta:
        model = Tournament
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.initial["status"] = Tournament.Status.UPCOMING
            # New entries created from the dedicated BR proxy admin are always paid unlimited BR rounds.
            if self.instance._meta.proxy and self.instance._meta.model_name == "unlimitedtournament":
                self.initial["is_unlimited_br"] = True
            if self.instance._meta.proxy and self.instance._meta.model_name == "diwalioffertournament":
                self.initial.update({
                    "mode": Tournament.Mode.BR, "br_format": Tournament.BRFormat.SOLO,
                    "entry_fee": Decimal("1.00"), "max_players": 49,
                    "is_unlimited_br": True, "auto_start_at_capacity": True,
                })
                self.fields["start_time"].required = False
        if "gender_category" in self.fields:
            self.fields["gender_category"].required = False
        self.fields["status"].help_text = (
            "Website par dikhane aur registration kholne ke liye "
            "'Upcoming' select karein. Draft tournaments public list mein nahi dikhte."
        )
        if "auto_reopen" in self.fields:
            self.fields["auto_reopen"].help_text = (
                "Internal recurring-series setting; normal tournaments mein zaroorat nahi."
            )
        self.fields["winner_uid"].label = "First Place Winner — Free Fire UID"
        self.fields["winner_uid"].help_text = (
            "Tournament ka first-place player choose karne ke liye us verified registration ki Free Fire UID enter karein. "
            "Leaderboard par us player ko first place dikhaya jayega; prize payout alag se manually verify karna hoga."
        )

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("gender_category"):
            cleaned["gender_category"] = Tournament.GenderCategory.OPEN
        # The dedicated proxy admin must never create a normal/non-series tournament.
        if self.instance._meta.proxy and self.instance._meta.model_name == "unlimitedtournament":
            cleaned["is_unlimited_br"] = True
        if self.instance._meta.proxy and self.instance._meta.model_name == "diwalioffertournament":
            cleaned.update({
                "mode": Tournament.Mode.BR,
                "br_format": Tournament.BRFormat.SOLO,
                "vs_format": "",
                "gender_category": Tournament.GenderCategory.OPEN,
                "entry_fee": Decimal("1.00"),
                "max_players": 49,
                "is_unlimited_br": True,
                "is_diwali_offer": True,
                "is_free_fan_tournament": False,
                "auto_start_at_capacity": True,
                "start_time": cleaned.get("start_time") or timezone.now(),
            })
        if cleaned.get("mode") == Tournament.Mode.BR and cleaned.get("vs_format"):
            self.add_error("vs_format", "BR tournament ke liye CS/VS format khaali rakhein.")
        if cleaned.get("mode") == Tournament.Mode.BR and not cleaned.get("br_format"):
            # Older/simple admin submissions may omit the optional format; keep them usable as Solo.
            cleaned["br_format"] = Tournament.BRFormat.SOLO
        if cleaned.get("mode") == Tournament.Mode.VS and cleaned.get("br_format"):
            self.add_error("br_format", "CS/VS tournament ke liye BR format khaali rakhein.")
        if cleaned.get("mode") == Tournament.Mode.VS and not cleaned.get("vs_format"):
            self.add_error("vs_format", "CS/VS tournament ke liye 1v1, 2v2, 3v3 ya 4v4 format chunein.")
        if cleaned.get("is_unlimited_br"):
            if cleaned.get("mode") != Tournament.Mode.BR:
                self.add_error("mode", "Unlimited series sirf Battle Royale (BR) mode mein ho sakti hai.")
            br_format = cleaned.get("br_format") or Tournament.BRFormat.SOLO
            capacities = {
                Tournament.BRFormat.SOLO: 49,
                Tournament.BRFormat.DUO: 48,
                Tournament.BRFormat.SQUAD: 48,
            }
            cleaned["br_format"] = br_format
            cleaned["max_players"] = capacities.get(br_format, 49)
            cleaned["auto_start_at_capacity"] = True
        elif cleaned.get("auto_reopen"):
            self.add_error("auto_reopen", "Auto reopen sirf Unlimited BR series ke liye hai.")

        # Room credentials must be saved in the same admin submission that makes it LIVE.
        if cleaned.get("status") == Tournament.Status.LIVE:
            if not (cleaned.get("room_id") or "").strip():
                self.add_error("room_id", "Tournament LIVE karne se pehle Room ID bharo.")
            if not (cleaned.get("room_password") or "").strip():
                self.add_error("room_password", "Tournament LIVE karne se pehle Room Password bharo.")
        return cleaned


class RegistrationInline(admin.TabularInline):
    model = Registration
    extra = 0
    show_change_link = True
    fields = (
        "player", "player_contact", "player_payout_qr", "free_fire_uid",
        "payment_method", "currency_amount", "entry_fee_paid",
        "payment_reference", "payment_verified", "status", "verification_photo",
        "team_number", "team_position", "room_details_sent", "ready_deadline", "ready_confirmed_at",
        "refund_processed", "refund_reference", "registered_at",
    )
    readonly_fields = (
        "player", "player_contact", "player_payout_qr", "free_fire_uid",
        "payment_method", "currency_amount", "entry_fee_paid", "payment_reference",
        "verification_photo", "team_number", "team_position", "room_details_sent", "ready_deadline",
        "ready_confirmed_at", "refund_processed", "refund_reference", "registered_at",
    )
    can_delete = False
    ordering = ("registered_at",)

    @admin.display(description="Player email / phone")
    def player_contact(self, obj):
        return f"{obj.player.email or 'No email'} · {getattr(obj.player, 'phone_number', '') or 'No phone'}"

    @admin.display(description="Player UPI QR")
    def player_payout_qr(self, obj):
        photo = getattr(obj.player, "upi_qr_code", None)
        if not photo:
            return "No payout QR uploaded in profile"
        try:
            return format_html(
                '<a href="{}" target="_blank" rel="noopener"><img src="{}" width="76" height="76" style="object-fit:contain;background:#fff;padding:4px;border-radius:6px" alt="Player payout UPI QR"></a>',
                photo.url, photo.url,
            )
        except (ValueError, OSError):
            return "UPI QR uploaded but unavailable"


class KillSubmissionInline(admin.TabularInline):
    model = KillSubmission
    extra = 0
    show_change_link = True
    fields = (
        "player", "registered_uid", "free_fire_uid", "history_video",
        "history_image_one", "history_image_two", "ai_proposed_kills",
        "ai_confidence", "ai_uid_matches", "ai_review_notes", "approved_kills",
        "proposed_reward", "approved_reward", "status", "admin_notes",
        "payout_reference", "payout_status", "payout_paid_at", "submitted_at",
    )
    readonly_fields = (
        "player", "registered_uid", "free_fire_uid", "history_video",
        "history_image_one", "history_image_two", "ai_proposed_kills",
        "ai_confidence", "ai_uid_matches", "ai_review_notes", "proposed_reward",
        "payout_status", "payout_paid_at", "submitted_at",
    )
    can_delete = False
    ordering = ("-submitted_at",)



@admin.action(description="Cancel tournament and refund registered players")
def cancel_and_refund_tournaments(modeladmin, request, queryset):
    cancelled = 0
    refunded = 0
    for tournament in queryset:
        count, message = cancel_tournament_and_refund(tournament.pk)
        if "already cancelled" not in message.lower():
            cancelled += 1
        refunded += count
    modeladmin.message_user(
        request,
        f"{cancelled} tournament(s) cancelled; {refunded} player refund(s) recorded.",
        messages.SUCCESS,
    )


@admin.action(description="Mark winner prize PAID after manual UPI transfer and real UTR entry")
def mark_winner_prizes_paid(modeladmin, request, queryset):
    paid = 0
    skipped = 0
    for selected in queryset:
        with transaction.atomic():
            tournament = Tournament.objects.select_for_update().get(pk=selected.pk)
            if tournament.winner_prize_paid or not tournament.winner_uid or tournament.prize_pool <= 0 or (tournament.mode == Tournament.Mode.BR and tournament.br_format != "solo"):
                skipped += 1
                continue
            utr = (tournament.winner_prize_reference or "").strip()
            if len(utr) < 6 or utr.startswith("WIN-PRIZE-"):
                skipped += 1
                continue
            if Tournament.objects.filter(winner_prize_reference__iexact=utr).exclude(pk=tournament.pk).exists():
                skipped += 1
                continue
            eligible = Registration.objects.select_for_update().filter(
                tournament=tournament,
                free_fire_uid=str(tournament.winner_uid).strip(),
                payment_verified=True,
                refund_processed=False,                status__in=[Registration.Status.CONFIRMED, Registration.Status.WAITING_READY, Registration.Status.READY],
            ).select_related("player")
            if eligible.count() != 1:
                skipped += 1
                continue
            winner = eligible.first()
            if not (winner.player.upi_id or "").strip() and not winner.player.upi_qr_code:
                skipped += 1
                continue
            admin_wallet, _ = AdminWallet.objects.get_or_create(name="Main Admin Wallet")
            admin_wallet = AdminWallet.objects.select_for_update().get(pk=admin_wallet.pk)
            prize = tournament.prize_pool
            if admin_wallet.balance < prize:
                skipped += 1
                continue
            ledger_reference = f"ADMIN-WIN-UPI-{tournament.pk}"
            if AdminWalletTransaction.objects.filter(reference=ledger_reference).exists():
                skipped += 1
                continue
            # Real transfer must already be sent externally to the winner's saved UPI ID/QR.
            admin_wallet.balance -= prize
            admin_wallet.save(update_fields=["balance", "updated_at"])
            AdminWalletTransaction.objects.create(
                admin_wallet=admin_wallet,
                transaction_type=AdminWalletTransaction.TransactionType.PRIZE,
                amount=prize,
                status=AdminWalletTransaction.Status.COMPLETED,
                reference=ledger_reference,
                description=f"Manual UPI winner prize for tournament {tournament.pk}; external UTR {utr}; player profile {winner.player_id}.",
            )
            tournament.winner_prize_paid = True
            tournament.save(update_fields=["winner_prize_paid", "updated_at"])
            paid += 1
    if paid:
        modeladmin.message_user(request, f"{paid} winner prize(s) marked paid after manual UPI transfer.", messages.SUCCESS)
    if skipped:
        modeladmin.message_user(request, f"{skipped} winner prize(s) skipped: check winner UID, saved UPI/QR, real unique UTR and Admin Wallet ledger balance.", messages.WARNING)


@admin.action(description="Award BR Diamonds / VS Fan Tokens to selected tournament winner")
def award_arena_currency_winner(modeladmin, request, queryset):
    """Credit non-cash tournament prizes once; separate from any manual UPI prize."""
    from apps.social.models import PlayerShopWallet

    awarded = 0
    skipped = 0
    for selected in queryset:
        with transaction.atomic():
            tournament = Tournament.objects.select_for_update().get(pk=selected.pk)
            if tournament.status != Tournament.Status.COMPLETED or tournament.is_free_fan_tournament or (tournament.mode == Tournament.Mode.BR and tournament.br_format != "solo"):
                skipped += 1
                continue
            winner_uid = str(tournament.winner_uid or "").strip()
            winners = Registration.objects.select_for_update().filter(
                tournament=tournament,
                free_fire_uid=winner_uid,
                payment_verified=True,
                refund_processed=False,
                status__in=[Registration.Status.CONFIRMED, Registration.Status.WAITING_READY, Registration.Status.READY],
            ).select_related("player")
            if not winner_uid or winners.count() != 1:
                skipped += 1
                continue
            registration = winners.first()
            reference = f"ARENA-CURRENCY-WIN-{tournament.pk}"
            if TournamentLedgerEntry.objects.filter(reference=reference).exists() or TournamentLedgerEntry.objects.filter(reference__startswith=f"{reference}-").exists():
                skipped += 1
                continue
            wallet, _ = PlayerShopWallet.objects.get_or_create(user=registration.player)
            wallet = PlayerShopWallet.objects.select_for_update().get(pk=wallet.pk)
            if tournament.mode == Tournament.Mode.BR:
                wallet.diamonds += 50
                wallet.save(update_fields=["diamonds", "updated_at"])
                TournamentLedgerEntry.objects.create(
                    tournament=tournament, player=registration.player, registration=registration,
                    entry_type=TournamentLedgerEntry.EntryType.REWARD,
                    currency=TournamentLedgerEntry.Currency.DIAMONDS, quantity=50,
                    amount_inr=Decimal("0.00"), status=TournamentLedgerEntry.Status.COMPLETED,
                    reference=reference, description="Admin-approved BR winner prize: 50 Diamonds",
                )
            else:
                # VS winner prizes are paid manually by the admin, never auto-credited here.
                skipped += 1
                continue
            awarded += 1
    if awarded:
        modeladmin.message_user(request, f"{awarded} winner non-cash reward(s) credited to player wallet.", messages.SUCCESS)
    if skipped:
        modeladmin.message_user(request, f"{skipped} skipped: set the correct Winner UID, verify the player's registration/payment, mark tournament Completed, and check that no reward was already credited.", messages.WARNING)


@admin.action(description="Duo/Squad winner team: give each listed player 10 Fan Currency")
def award_br_winner_team(modeladmin, request, queryset):
    """Credit each verified winner once, with one ledger entry per currency and UID."""
    from apps.social.models import PlayerShopWallet

    awarded_players = 0
    skipped = 0
    for selected in queryset:
        with transaction.atomic():
            tournament = Tournament.objects.select_for_update().get(pk=selected.pk)
            if tournament.mode != Tournament.Mode.BR or tournament.br_format not in ("duo", "squad") or tournament.status != Tournament.Status.COMPLETED:
                skipped += 1
                continue
            uids = []
            for raw in (tournament.winner_team_uids or "").replace(",", "\n").splitlines():
                uid = raw.strip()
                if uid and uid not in uids:
                    uids.append(uid)
            expected_team_size = 2 if tournament.br_format == "duo" else 4
            if len(uids) != expected_team_size:
                skipped += 1
                continue
            registrations = list(Registration.objects.select_for_update().filter(
                tournament=tournament, free_fire_uid__in=uids, payment_verified=True,
                refund_processed=False,
                status__in=[Registration.Status.CONFIRMED, Registration.Status.WAITING_READY, Registration.Status.READY],
            ).select_related("player"))
            by_uid = {row.free_fire_uid: row for row in registrations}
            if len(by_uid) != len(uids):
                skipped += 1
                continue
            already_done = False
            for uid in uids:
                base = f"BR-TEAM-WIN-{tournament.pk}-{uid}"
                if TournamentLedgerEntry.objects.filter(reference__in=[base + "-FAN", base + "-COIN"]).exists():
                    already_done = True
                    break
            if already_done:
                skipped += 1
                continue
            for uid in uids:
                registration = by_uid[uid]
                wallet, _ = PlayerShopWallet.objects.get_or_create(user=registration.player)
                wallet = PlayerShopWallet.objects.select_for_update().get(pk=wallet.pk)
                wallet.fan_tokens += 10
                wallet.save(update_fields=["fan_tokens", "updated_at"])
                base = f"BR-TEAM-WIN-{tournament.pk}-{uid}"
                TournamentLedgerEntry.objects.create(
                    tournament=tournament, player=registration.player, registration=registration,
                    entry_type=TournamentLedgerEntry.EntryType.REWARD,
                    currency=TournamentLedgerEntry.Currency.FAN_TOKENS, quantity=10,
                    status=TournamentLedgerEntry.Status.COMPLETED, reference=base + "-FAN",
                    description="BR Duo/Squad winning team reward: 10 Fan Currency",
                )
                awarded_players += 1
    if awarded_players:
        modeladmin.message_user(request, f"{awarded_players} winning team player(s) received 10 Fan Currency each.", messages.SUCCESS)
    if skipped:
        modeladmin.message_user(request, f"{skipped} tournament(s) skipped: check BR mode, Completed status, every UID's verified paid registration, and duplicate payout records.", messages.WARNING)


@admin.action(description="Create a fresh next round; keep this completed round and its history unchanged")
def create_next_round_preserving_history(modeladmin, request, queryset):
    created = 0
    skipped = 0
    for selected in queryset:
        with transaction.atomic():
            old = Tournament.objects.select_for_update().get(pk=selected.pk)
            if old.status != Tournament.Status.COMPLETED:
                skipped += 1
                continue
            root = old.series_root or old
            if root.series_rounds.filter(status=Tournament.Status.UPCOMING).exists():
                skipped += 1
                continue
            round_number = root.series_rounds.count() + 2
            new_round = Tournament.objects.create(
                title=f"{root.title} - Round {round_number}"[:120],
                mode=old.mode, br_format=old.br_format, vs_format=old.vs_format,
                gender_category=old.gender_category, description=old.description,
                entry_fee=old.entry_fee, prize_pool=old.prize_pool,
                max_players=old.max_players, start_time=timezone.now() + timedelta(minutes=10),
                status=Tournament.Status.UPCOMING, is_unlimited_br=old.is_unlimited_br,
                is_free_fan_tournament=old.is_free_fan_tournament,
                winner_coins_prize=old.winner_coins_prize,
                auto_start_at_capacity=old.auto_start_at_capacity,
                auto_reopen=old.auto_reopen, series_root=root,
            )
            created += 1
    if created:
        modeladmin.message_user(request, f"{created} new round(s) created. Previous round records and leaderboards remain unchanged.", messages.SUCCESS)
    if skipped:
        modeladmin.message_user(request, f"{skipped} skipped: select only Completed tournaments and ensure no Upcoming round already exists in that series.", messages.WARNING)


@admin.action(description="Award 20 Diwali Diamonds to the verified winner")
def award_diwali_winner_diamonds(modeladmin, request, queryset):
    """Credit the Diwali first prize once to the unique verified tournament winner."""
    from apps.social.models import PlayerShopWallet

    awarded = 0
    skipped = 0
    for selected in queryset:
        with transaction.atomic():
            tournament = Tournament.objects.select_for_update().get(pk=selected.pk)
            if (
                not tournament.is_diwali_offer
                or tournament.status != Tournament.Status.COMPLETED
                or not str(tournament.winner_uid or "").strip()
            ):
                skipped += 1
                continue
            winners = Registration.objects.select_for_update().filter(
                tournament=tournament,
                free_fire_uid=str(tournament.winner_uid).strip(),
                payment_verified=True,
                refund_processed=False,
                status__in=[Registration.Status.CONFIRMED, Registration.Status.WAITING_READY, Registration.Status.READY],
            ).select_related("player")
            if winners.count() != 1:
                skipped += 1
                continue
            registration = winners.first()
            reference = f"DIWALI-WINNER-20-DIAMONDS-{tournament.pk}"
            if TournamentLedgerEntry.objects.filter(reference=reference).exists():
                skipped += 1
                continue
            wallet, _ = PlayerShopWallet.objects.get_or_create(user=registration.player)
            wallet = PlayerShopWallet.objects.select_for_update().get(pk=wallet.pk)
            wallet.diamonds += 20
            wallet.save(update_fields=("diamonds", "updated_at"))
            TournamentLedgerEntry.objects.create(
                tournament=tournament,
                player=registration.player,
                registration=registration,
                entry_type=TournamentLedgerEntry.EntryType.REWARD,
                currency=TournamentLedgerEntry.Currency.DIAMONDS,
                quantity=20,
                amount_inr=Decimal("0.00"),
                status=TournamentLedgerEntry.Status.COMPLETED,
                reference=reference,
                description="Diwali Solo BR first-place prize: 20 Diamonds, admin-confirmed winner.",
            )
            awarded += 1
    if awarded:
        modeladmin.message_user(request, f"{awarded} Diwali winner(s) received 20 Diamonds.", messages.SUCCESS)
    if skipped:
        modeladmin.message_user(request, f"{skipped} skipped: select only completed Diwali rounds, set a unique verified Winner UID, and check the reward ledger for duplicates.", messages.WARNING)


@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
    form = TournamentAdminForm
    exclude = ("is_unlimited_br", "is_free_fan_tournament", "auto_start_at_capacity", "auto_reopen", "series_root")
    list_display = (
        "title", "open_tournament_control", "mode", "br_format", "vs_format", "gender_category",
        "entry_fee", "prize_pool", "max_players", "start_time", "status", "winner_prize_paid",
    )
    list_filter = ("mode", "br_format", "vs_format", "gender_category", "status", "start_time")
    search_fields = ("title", "description")
    ordering = ("start_time",)
    # Keep tournament setup separate from registrations and kill evidence.
    # Those have their own admin sections so adding/editing a tournament stays manageable.
    inlines = ()
    actions = (cancel_and_refund_tournaments, mark_winner_prizes_paid, award_arena_currency_winner, award_br_winner_team, create_next_round_preserving_history,)
    readonly_fields = (
        "tournament_control_panel", "winner_prize_paid",
        "kill_prize_distributed", "kill_prize_pool", "kill_prize_reference",
        "winner_payout_destination", "winner_payout_qr",
    )

    def get_queryset(self, request):
        # Keep free and unlimited series in their own proxy-admin menus.
        return super().get_queryset(request).filter(is_unlimited_br=False, is_free_fan_tournament=False)

    @admin.display(description="Tournament Control")
    def open_tournament_control(self, obj):
        url = reverse("tournaments:admin_tournament_dashboard", args=[obj.pk])
        return format_html('<a class="button" href="{}">Open control panel</a>', url)

    @admin.display(description="Tournament Control Panel")
    def tournament_control_panel(self, obj):
        if not obj or not obj.pk:
            return "Save this tournament first; then open its separate control panel."
        url = reverse("tournaments:admin_tournament_dashboard", args=[obj.pk])
        return format_html(
            '<a class="button" href="{}">Open {} — full tournament process</a>',
            url, obj.title,
        )

    def save_model(self, request, obj, form, change):
        previous_status = None
        if change and obj.pk:
            previous_status = Tournament.objects.filter(pk=obj.pk).values_list("status", flat=True).first()

        # All newly-created paid BR events belong to the unlimited BR series and its public listing.
        # Free Fan events remain separate; CS/VS events are not changed by this rule.
        if not change and obj.mode == Tournament.Mode.BR and not obj.is_free_fan_tournament:
            obj.is_unlimited_br = True
            obj.auto_start_at_capacity = True
            capacities = {
                Tournament.BRFormat.SOLO: 49,
                Tournament.BRFormat.DUO: 48,
                Tournament.BRFormat.SQUAD: 48,
            }
            obj.max_players = capacities.get(obj.br_format or Tournament.BRFormat.SOLO, 49)
            obj.br_format = obj.br_format or Tournament.BRFormat.SOLO

        was_live = previous_status == Tournament.Status.LIVE
        super().save_model(request, obj, form, change)

        # Re-open a fresh no-date 49-player round only after admin marks the current round complete.
        if obj.status == Tournament.Status.COMPLETED and previous_status != Tournament.Status.COMPLETED:
            root = Tournament.objects.get(pk=obj.series_root_id or obj.pk)
            if root.auto_reopen and not root.series_rounds.filter(status=Tournament.Status.UPCOMING).exists():
                next_round_number = root.series_rounds.count() + 2
                Tournament.objects.create(
                    title=f"{root.title} - Round {next_round_number}"[:120],
                    mode=Tournament.Mode.BR, br_format=root.br_format or Tournament.BRFormat.SOLO,
                    vs_format="", description=root.description,
                    entry_fee=Decimal("0.00") if root.is_free_fan_tournament else root.entry_fee,
                    prize_pool=root.prize_pool, max_players=root.max_players,
                    start_time=timezone.now() + timedelta(minutes=10),
                    status=Tournament.Status.UPCOMING, is_unlimited_br=True,
                    is_free_fan_tournament=root.is_free_fan_tournament,
                    winner_coins_prize=root.winner_coins_prize,
                    auto_start_at_capacity=True, auto_reopen=True, series_root=root,
                )

        # Publish room access only when admin moves the tournament into LIVE.
        if obj.status != Tournament.Status.LIVE or was_live:
            return

        from datetime import timedelta
        from django.conf import settings
        from django.core.mail import send_mail
        from django.urls import reverse
        from django.utils import timezone

        if obj.is_unlimited_br or obj.mode == Tournament.Mode.VS:
            try:
                assign_teams_for_tournament(obj.pk)
            except ValueError as exc:
                obj.status = Tournament.Status.UPCOMING
                obj.save(update_fields=["status", "updated_at"])
                messages.error(request, str(exc))
                return

        now = timezone.now()
        eligible_ids = list(Registration.objects.filter(
            tournament=obj,
            payment_verified=True,
            refund_processed=False,
            status=Registration.Status.CONFIRMED,
        ).values_list("pk", flat=True))
        Registration.objects.filter(pk__in=eligible_ids).update(
            status=Registration.Status.WAITING_READY,
            room_details_sent=True,
            ready_deadline=now + timedelta(seconds=PLAYER_CONFIRMATION_TIMEOUT_SECONDS),
            ready_confirmed_at=None,
        )

        sent = 0
        missing_email = 0
        for registration in Registration.objects.filter(pk__in=eligible_ids).select_related("player"):
            player = registration.player
            if not (player.email or "").strip():
                missing_email += 1
                continue
            try:
                room_url = request.build_absolute_uri(
                    reverse("tournaments:player_room", args=[registration.pk])
                )
                delivered = send_mail(
                    subject=f"FF Arena: {obj.title} is LIVE — confirm YES/NO",
                    message=(
                        f"Hi {player.username},\n\n"
                        f"Tournament: {obj.title} is now LIVE.\n"
                        f"Your registered Free Fire UID: {registration.free_fire_uid}\n"
                        f"Entry fee: INR {registration.entry_fee_paid}\n\n"
                        "Open the secure tournament page and press YES if you want to play, "
                        "or NO if you cannot play. Room ID/password are shown only after YES. "
                        "Please respond within 5 minutes. If you press NO or do not respond, "
                        "you will be marked NOT PLAYING. If your entry was paid directly by UPI, "
                        "the admin must send the real refund and record its UTR; the website "
                        "cannot transfer money automatically.\n\n"
                        f"Confirm here: {room_url}\n"
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[player.email],
                    fail_silently=False,
                )
                sent += delivered
            except Exception:
                # Keep the tournament LIVE, but report notification failure to the admin.
                messages.warning(request, f"Email could not be sent to {player.email}. Check Render SMTP environment variables and provider logs.")
                continue

        self.message_user(
            request,
            f"Tournament is LIVE. {len(eligible_ids)} verified player(s) were queued for YES/NO for 5 minutes; "
            f"emails successfully handed to SMTP: {sent}, players without email: {missing_email}. "
            "Check SMTP provider logs for final delivery.",
            level=messages.SUCCESS,
        )

    def get_actions(self, request):
        actions = super().get_actions(request)
        # Never bulk-delete tournament records: they can have payment/refund audit trails.
        actions.pop("delete_selected", None)
        return actions

    def has_delete_permission(self, request, obj=None):
        if obj is not None:
            # Keep financial/registration history intact. Empty tournaments can still be deleted.
            if obj.registrations.exists() or TournamentLedgerEntry.objects.filter(tournament=obj).exists():
                return False
        return super().has_delete_permission(request, obj)

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if obj and obj.winner_prize_paid:
            fields.append("winner_uid")
        return tuple(fields)

    @admin.display(description="Winner UPI destination")
    def winner_payout_destination(self, obj):
        if not obj or not obj.pk or not obj.winner_uid:
            return "Set Winner UID first; then reload to view payout details."
        registrations = Registration.objects.filter(
            tournament=obj, free_fire_uid=str(obj.winner_uid).strip(), payment_verified=True
        ).select_related("player")
        if registrations.count() != 1:
            return "No unique verified registration matches this Winner UID."
        player = registrations.first().player
        if (player.upi_id or "").strip():
            return f"Profile #{player.pk} · {player.username} · UPI ID saved"
        if player.upi_qr_code:
            return f"Profile #{player.pk} · {player.username} · use uploaded QR below"
        return f"Profile #{player.pk} · {player.username} · no UPI ID/QR saved"

    @admin.display(description="Winner UPI QR")
    def winner_payout_qr(self, obj):
        if not obj or not obj.pk or not obj.winner_uid:
            return "Set Winner UID first."
        registration = Registration.objects.filter(
            tournament=obj, free_fire_uid=str(obj.winner_uid).strip(), payment_verified=True
        ).select_related("player").first()
        if not registration:
            return "No verified registration matches this Winner UID."
        player = registration.player
        if player.upi_qr_code:
            try:
                return format_html(
                    '<a href="{}" target="_blank" rel="noopener"><img src="{}" width="120" height="120" alt="Winner uploaded UPI QR" /></a>',
                    player.upi_qr_code.url, player.upi_qr_code.url,
                )
            except (ValueError, OSError):
                pass
        if not (player.upi_id or "").strip() or "@" not in player.upi_id:
            return "Winner has not supplied a usable UPI ID or QR."
        import base64
        import io
        from urllib.parse import urlencode
        import qrcode
        uri = "upi://pay?" + urlencode({
            "pa": player.upi_id.strip(),
            "pn": player.username[:50],
            "am": f"{obj.prize_pool:.2f}",
            "cu": "INR",
            "tn": f"FF winner prize tournament {obj.pk}",
        })
        image = qrcode.make(uri)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return format_html('<img src="data:image/png;base64,{}" width="120" height="120" alt="Winner UPI payment QR" />', encoded)
    fieldsets = (
        ("1. Tournament Details — kya ban raha hai?", {"description": "Title public tournament name hai. Mode mein BR ya CS/VS chunein. CS/VS mein 1v1/2v2/3v3/4v4 format chunein. Gender Category se Open, Boys Only, Girls Only ya Girls vs Boys event banayein. Har saved tournament ka apna alag control panel hai.", "fields": ("tournament_control_panel", "title", "description", "mode", "br_format", "vs_format", "gender_category")}),
        ("2. Fees & Players — entry aur capacity", {"description": "Entry Fee player se li jane wali registration fee hai. Prize Pool tournament ka first-place prize hai; ise admin ke funds aur payout process ke mutabik set karein. Max Players room capacity hai (maximum 49). BR format Solo/Duo/Squad chunein. Normal BR mein har approved kill par 5 Diamonds; minimum 2 verified kills. Free Fan event ka alag Fan Token rule rahega. Evidence verification zaroori hai.", "fields": ("entry_fee", "prize_pool", "max_players")}),
        ("4. Schedule & Status — publish / LIVE", {"description": "Start Time tournament ka scheduled time hai. Draft public list mein nahi dikhta; Upcoming se listing/registration khulti hai. LIVE karne se pehle Room Details section mein Room ID aur Password bharna zaroori hai. LIVE karne par verified paid players ko YES/NO confirmation email bhejne ki koshish hoti hai; email delivery SMTP setup par depend karti hai.", "fields": ("start_time", "status")}),
        ("5. Room Details — private until YES", {"description": "Room ID aur Password game room ke credentials hain. Tournament LIVE karte waqt dono bharein. Player ko room tabhi dikhega jab woh deadline ke andar YES kare. Credentials public description/website post mein na likhein.", "fields": ("room_id", "room_password")}),
        ("6. BR Winning Team Rewards", {"description": "Tournament Completed hone ke baad winning BR team ke har player ka registered Free Fire UID yahan alag line ya comma se likhein. Admin action se har verified winner ko 10 Fan Tokens + 50 Coins ek hi baar milenge; har reward ledger mein save hoga.", "fields": ("winner_team_uids",)}),
        ("7. First Place Winner & payout tracking", {"description": "Tournament complete/review ke baad winner ki registered Free Fire UID enter karein. Neeche player ki saved UPI/QR details dekh sakte hain. Winner Prize Reference mein actual transfer ka real UTR enter karne ke baad hi payout action use karein. Is field ko bharna apne-aap paise transfer nahi karta.", "fields": ("winner_uid", "winner_payout_destination", "winner_payout_qr", "winner_prize_reference", "winner_prize_paid")}),
    )


@admin.action(description="Verify UTR against actual UPI/bank receipt and confirm entry")
def verify_entry_payments(modeladmin, request, queryset):
    verified_count = 0
    skipped_count = 0

    with transaction.atomic():
        for registration in queryset.select_related("tournament", "player").select_for_update():
            if registration.payment_verified or registration.status != Registration.Status.PENDING_PAYMENT:
                skipped_count += 1
                continue

            fee = registration.entry_fee_paid
            utr = (registration.payment_reference or "").strip()
            if fee > 0:
                # Admin must check the actual receiving UPI/bank statement first.
                if len(utr) < 6:
                    skipped_count += 1
                    continue
                duplicate_utr = Registration.objects.filter(
                    payment_reference__iexact=utr
                ).exclude(pk=registration.pk).exists()
                if duplicate_utr:
                    skipped_count += 1
                    continue

                admin_reference = f"ADMIN-ENTRY-{registration.pk}"
                if AdminWalletTransaction.objects.filter(reference=admin_reference).exists():
                    skipped_count += 1
                    continue

                admin_wallet, _ = AdminWallet.objects.get_or_create(name="Main Admin Wallet")
                admin_wallet = AdminWallet.objects.select_for_update().get(pk=admin_wallet.pk)
                admin_wallet.balance += fee
                admin_wallet.save(update_fields=["balance", "updated_at"])
                AdminWalletTransaction.objects.create(
                    admin_wallet=admin_wallet,
                    transaction_type=AdminWalletTransaction.TransactionType.ENTRY_FEE,
                    amount=fee,
                    status=AdminWalletTransaction.Status.COMPLETED,
                    reference=admin_reference,
                    description=f"Manually verified UTR {utr} for tournament {registration.tournament_id}; admin checked actual bank/UPI receipt.",
                )

            registration.payment_verified = True
            registration.status = Registration.Status.CONFIRMED
            registration.save(update_fields=["payment_verified", "status", "updated_at"])
            TournamentLedgerEntry.objects.filter(
                registration=registration,
                entry_type=TournamentLedgerEntry.EntryType.ENTRY,
            ).update(
                status=TournamentLedgerEntry.Status.COMPLETED,
                description="Tournament entry payment verified by admin against the actual payment receipt.",
            )
            if registration.tournament.auto_start_at_capacity:
                from .registration_services import maybe_start_unlimited_tournament
                maybe_start_unlimited_tournament(registration.tournament_id)
            verified_count += 1

    if verified_count:
        modeladmin.message_user(
            request,
            f"{verified_count} registration(s) confirmed after admin verification. Actual UPI/bank statement check required before this action.",
            messages.SUCCESS,
        )
    if skipped_count:
        modeladmin.message_user(
            request,
            f"{skipped_count} registration(s) skipped: already verified, missing/duplicate UTR, or transaction already recorded.",
            messages.WARNING,
        )


@admin.action(description="Mark UPI refunds paid after sending actual refund and entering its UTR")
def mark_manual_upi_refunds_paid(modeladmin, request, queryset):
    completed = 0
    skipped = 0
    for selected in queryset:
        with transaction.atomic():
            registration = Registration.objects.select_for_update().select_related("tournament", "player").get(pk=selected.pk)
            utr = (registration.refund_reference or "").strip()
            if (
                not registration.payment_reference
                or not registration.payment_verified
                or registration.status not in (Registration.Status.CANCELLED, Registration.Status.NOT_PLAYING)
                or registration.refund_processed
                or len(utr) < 6
            ):
                skipped += 1
                continue
            if Registration.objects.filter(refund_reference__iexact=utr).exclude(pk=registration.pk).exists():
                skipped += 1
                continue
            ledger_reference = f"ADMIN-UPI-REFUND-{registration.pk}"
            if AdminWalletTransaction.objects.filter(reference=ledger_reference).exists():
                skipped += 1
                continue
            admin_wallet, _ = AdminWallet.objects.get_or_create(name="Main Admin Wallet")
            admin_wallet = AdminWallet.objects.select_for_update().get(pk=admin_wallet.pk)
            amount = registration.entry_fee_paid
            if admin_wallet.balance < amount:
                skipped += 1
                continue
            # This action only records a refund already sent outside the website through UPI.
            admin_wallet.balance -= amount
            admin_wallet.save(update_fields=["balance", "updated_at"])
            AdminWalletTransaction.objects.create(
                admin_wallet=admin_wallet,
                transaction_type=AdminWalletTransaction.TransactionType.REFUND,
                amount=amount,
                status=AdminWalletTransaction.Status.COMPLETED,
                reference=ledger_reference,
                description=f"Manual UPI refund UTR {utr} for cancelled/not-playing registration {registration.pk}",
            )
            registration.status = Registration.Status.REFUNDED
            registration.refund_processed = True
            registration.refund_processed_at = timezone.now()
            registration.save(update_fields=["status", "refund_processed", "refund_processed_at", "updated_at"])
            completed += 1
    if completed:
        modeladmin.message_user(request, f"{completed} manual UPI refund(s) recorded after transfer.", messages.SUCCESS)
    if skipped:
        modeladmin.message_user(request, f"{skipped} refund(s) skipped: verify payment/status, enter unique real UTR, and check Admin Wallet ledger balance.", messages.WARNING)


@admin.register(UnlimitedTournament)
class UnlimitedTournamentAdmin(TournamentAdmin):
    """Dedicated admin list for paid BR Solo/Duo/Squad unlimited events."""

    # Unlike the general Tournament admin, this proxy exposes its series controls.
    exclude = ("is_free_fan_tournament",)

    def get_fieldsets(self, request, obj=None):
        fieldsets = list(super().get_fieldsets(request, obj))
        fieldsets.insert(
            2,
            ("3. Unlimited BR Series", {
                "description": "Paid BR Solo/Duo/Squad series settings. New records in this section are automatically marked as Unlimited BR. Capacity is set from the selected format.",
                "fields": ("is_unlimited_br", "auto_start_at_capacity", "auto_reopen", "series_root"),
            }),
        )
        return tuple(fieldsets)

    def get_queryset(self, request):
        return super(TournamentAdmin, self).get_queryset(request).filter(
            is_unlimited_br=True,
            is_free_fan_tournament=False,
            mode=Tournament.Mode.BR,
        )


@admin.register(FreeFanTournament)
class FreeFanTournamentAdmin(admin.ModelAdmin):
    """Dedicated admin list for the existing Free Fan Tournament proxy."""
    list_display = ("id", "title", "status", "max_players", "start_time", "created_at")
    list_filter = ("status", "mode", "br_format")
    search_fields = ("title",)
    ordering = ("-created_at",)


@admin.register(DiwaliOfferTournament)
class DiwaliOfferTournamentAdmin(TournamentAdmin):
    """Dedicated Festival / Offers admin page; all round records remain separate from regular BR."""

    exclude = (
        "is_unlimited_br", "is_free_fan_tournament", "is_diwali_offer",
        "auto_start_at_capacity", "auto_reopen", "series_root", "start_time",
    )
    list_display = ("title", "open_tournament_control", "entry_fee", "max_players", "status", "winner_uid", "created_at")
    list_filter = ("status",)
    ordering = ("-created_at",)
    actions = (cancel_and_refund_tournaments, award_diwali_winner_diamonds)

    def get_queryset(self, request):
        return super(TournamentAdmin, self).get_queryset(request).filter(
            is_diwali_offer=True,
            mode=Tournament.Mode.BR,
            br_format=Tournament.BRFormat.SOLO,
        )

    def get_fieldsets(self, request, obj=None):
        return (
            ("🪔 Diwali Festival Offer — Solo BR", {
                "description": "Yeh event regular BR se alag hai. System fixed rakha gaya hai: 1 Diamond entry, 49 Solo players, 20 Diamonds first prize, 5 Coins per approved kill, minimum 2 verified kills. Public page par date/time nahi dikhega.",
                "fields": ("tournament_control_panel", "title", "description", "entry_fee", "max_players", "status"),
            }),
            ("🎮 Private Room Details", {
                "description": "Round LIVE hone par eligible players ko room details private bhejne ke liye yahan Room ID aur Password set karein.",
                "fields": ("room_id", "room_password"),
            }),
            ("🏆 Winner & Diwali Prize", {
                "description": "Round Completed karne ke baad verified winner ka registered Free Fire UID enter karein. Neeche action se 20 Diamonds ek baar credit honge.",
                "fields": ("winner_uid",),
            }),
        )

    def save_model(self, request, obj, form, change):
        obj.is_diwali_offer = True
        obj.mode = Tournament.Mode.BR
        obj.br_format = Tournament.BRFormat.SOLO
        obj.vs_format = ""
        obj.gender_category = Tournament.GenderCategory.OPEN
        obj.entry_fee = Decimal("1.00")
        obj.max_players = 49
        obj.is_unlimited_br = True
        obj.is_free_fan_tournament = False
        obj.auto_start_at_capacity = True
        if not obj.start_time:
            obj.start_time = timezone.now()
        super().save_model(request, obj, form, change)


@admin.register(KillSubmission)
class KillSubmissionAdmin(admin.ModelAdmin):
    """Admin evidence queue; uploaded evidence and AI output remain auditable."""
    list_display = (
        "id", "tournament", "player", "registered_uid", "free_fire_uid",
        "ai_proposed_kills", "ai_confidence", "ai_uid_matches", "status",
        "payout_status", "submitted_at",
    )
    list_filter = ("status", "payout_status", "ai_confidence", "ai_uid_matches", "tournament__mode")
    search_fields = ("player__username", "registered_uid", "free_fire_uid", "tournament__title")
    list_select_related = ("player", "tournament", "registration")
    readonly_fields = (
        "registration", "player", "tournament", "registered_uid", "free_fire_uid",
        "history_video", "history_image_one", "history_image_two",
        "ai_proposed_kills", "ai_confidence", "ai_uid_matches", "ai_review_notes",
        "proposed_reward", "proposed_coins_reward", "submitted_at",
    )
    fields = (
        "registration", "player", "tournament", "registered_uid", "free_fire_uid",
        "history_video", "history_image_one", "history_image_two",
        "ai_proposed_kills", "ai_confidence", "ai_uid_matches", "ai_review_notes",
        "approved_kills", "proposed_reward", "approved_reward",
        "proposed_coins_reward", "approved_coins_reward", "status", "admin_notes",
        "payout_reference", "payout_status", "payout_paid_at", "submitted_at", "reviewed_at",
    )


@admin.register(TournamentLedgerEntry)
class TournamentLedgerEntryAdmin(admin.ModelAdmin):
    """Immutable audit view for entry, reward and refund ledger records."""
    list_display = (
        "id", "tournament", "player", "entry_type", "currency", "quantity",
        "amount_inr", "status", "reference", "created_at",
    )
    list_filter = ("entry_type", "currency", "status", "tournament__mode")
    search_fields = ("reference", "player__username", "tournament__title", "description")
    list_select_related = ("tournament", "player", "registration")
    readonly_fields = tuple(field.name for field in TournamentLedgerEntry._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = (
        "id", "tournament", "player", "player_gender", "player_profile_id", "free_fire_uid", "verification_selfie",
        "entry_fee_paid", "payment_method", "currency_amount", "payment_verified", "status", "room_details_sent",
        "refund_processed", "registered_at",
    )
    list_filter = ("payment_method", "status", "payment_verified", "refund_processed", "player__gender", "tournament__gender_category", "tournament__mode", "tournament")
    search_fields = (
        "free_fire_uid", "payment_reference", "player__username",
        "player__email", "player__phone_number", "tournament__title",
    )
    list_select_related = ("player", "tournament")
    readonly_fields = (
        "player_profile_id", "player_gender", "verification_selfie", "player_email", "player_phone", "player_photo",
        "player_upi_destination", "player_wallet_balance",
        "registered_at", "updated_at", "ready_confirmed_at", "refund_processed_at",
    )
    fieldsets = (
        ("1. Tournament & Registration", {
            "description": "Tournament, mode, player category aur registered Free Fire UID check karein. Girls vs Boys event ki selfie review karein; photo automatic proof nahi hai.",
            "fields": ("tournament", "player", "player_gender", "verification_selfie", "free_fire_uid", "status"),
        }),
        ("2. Player Contact & Payout Details", {
            "description": "Prize/refund ke liye player profile ki contact aur UPI details dekhein.",
            "fields": ("player_profile_id", "player_email", "player_phone", "player_photo", "player_upi_destination", "player_wallet_balance"),
        }),
        ("3. Entry Payment Verification", {
            "description": "UPI entries: actual UTR/bank receipt verify karein. Diamond/Coin entries: payment_method aur currency_amount audit karein; these were debited from the player's shop balance.",
            "fields": ("entry_fee_paid", "payment_method", "currency_amount", "payment_reference", "payment_submitted_at", "payment_verified"),
        }),
        ("4. Match / Room Readiness", {
            "description": "Room ID/password sirf eligible paid players ko share karein. Ready deadline aur confirmation check karein.",
            "fields": ("room_details_sent", "ready_deadline", "ready_confirmed_at"),
        }),
        ("5. Cancellation / Refund Tracking", {
            "description": "Actual UPI refund bhejne ke baad unique real refund UTR enter karein. List page par registration select karke refund action chalayein.",
            "fields": ("refund_processed", "refund_reference", "refund_processed_at"),
        }),
        ("Timestamps", {"fields": ("registered_at", "updated_at")}),
    )
    actions = (verify_entry_payments, mark_manual_upi_refunds_paid)

    @admin.display(description="Player Category", ordering="player__gender")
    def player_gender(self, obj):
        return obj.player.get_gender_display() or "Not selected"

    @admin.display(description="Registration Selfie")
    def verification_selfie(self, obj):
        photo = obj.verification_photo
        if photo:
            try:
                return format_html('<a href="{}" target="_blank" rel="noopener"><img src="{}" width="100" height="100" style="object-fit:cover;border-radius:10px" alt="Private registration selfie"></a>', photo.url, photo.url)
            except (ValueError, OSError):
                return "Selfie uploaded but unavailable"
        return "No registration selfie (not required for this event)"

    @admin.display(description="Player Profile ID", ordering="player__id")
    def player_profile_id(self, obj):
        return f"Profile #{obj.player_id}"

    @admin.display(description="Player Email")
    def player_email(self, obj):
        return obj.player.email or "Email not provided"

    @admin.display(description="Player Phone")
    def player_phone(self, obj):
        return obj.player.phone_number or "Phone not provided"

    @admin.display(description="Player Photo")
    def player_photo(self, obj):
        photo = obj.player.profile_photo
        if not photo:
            return "No profile photo"
        try:
            return format_html('<a href="{}" target="_blank" rel="noopener"><img src="{}" width="80" height="80" style="object-fit:cover;border-radius:8px" alt="Player profile photo"></a>', photo.url, photo.url)
        except (ValueError, OSError):
            return "Profile photo unavailable"

    @admin.display(description="Player UPI Details")
    def player_upi_destination(self, obj):
        player = obj.player
        upi = player.upi_id or "UPI ID not provided"
        if player.upi_qr_code:
            try:
                return format_html('{}<br><a href="{}" target="_blank" rel="noopener">Open player UPI QR</a>', upi, player.upi_qr_code.url)
            except (ValueError, OSError):
                return f"{upi} · QR unavailable"
        return upi

    @admin.display(description="Player Wallet Balance")
    def player_wallet_balance(self, obj):
        try:
            return f"₹{obj.player.wallet.balance}"
        except Exception:
            return "Wallet not created"
