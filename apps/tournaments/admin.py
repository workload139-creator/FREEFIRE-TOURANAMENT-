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
from .models import KillSubmission, Registration, Tournament, TournamentLedgerEntry, UnlimitedTournament, FreeFanTournament
from .services import cancel_tournament_and_refund
from .kill_services import reward_for_tournament


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
        self.fields["gender_category"].required = False
        self.fields["status"].help_text = (
            "Website par dikhane aur registration kholne ke liye "
            "'Upcoming' select karein. Draft tournaments public list mein nahi dikhte."
        )
        self.fields["auto_reopen"].help_text = (
            "Unlimited BR ke root tournament par ON/OFF karein: ON se 49-player round ke baad next round khulega."
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
        if cleaned.get("mode") == Tournament.Mode.BR and cleaned.get("vs_format"):
            self.add_error("vs_format", "BR tournament ke liye CS/VS format khaali rakhein.")
        if cleaned.get("mode") == Tournament.Mode.BR and not cleaned.get("is_unlimited_br") and not cleaned.get("is_free_fan_tournament") and not cleaned.get("br_format"):
            self.add_error("br_format", "BR tournament ke liye Solo, Duo ya Squad format chunein.")
        if cleaned.get("mode") == Tournament.Mode.VS and cleaned.get("br_format"):
            self.add_error("br_format", "CS/VS tournament ke liye BR format khaali rakhein.")
        if cleaned.get("mode") == Tournament.Mode.VS and not cleaned.get("vs_format"):
            self.add_error("vs_format", "CS/VS tournament ke liye 1v1, 2v2, 3v3 ya 4v4 format chunein.")
        if cleaned.get("is_unlimited_br"):
            if cleaned.get("mode") != Tournament.Mode.BR:
                self.add_error("mode", "Unlimited series sirf Battle Royale (BR) mode mein ho sakti hai.")
            if cleaned.get("max_players") != 49:
                self.add_error("max_players", "Unlimited BR round mein exactly 49 players hone chahiye.")
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
        "room_details_sent", "ready_deadline", "ready_confirmed_at",
        "refund_processed", "refund_reference", "registered_at",
    )
    readonly_fields = (
        "player", "player_contact", "player_payout_qr", "free_fire_uid",
        "payment_method", "currency_amount", "entry_fee_paid", "payment_reference",
        "verification_photo", "room_details_sent", "ready_deadline",
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
            if tournament.winner_prize_paid or not tournament.winner_uid or tournament.prize_pool <= 0:
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
                refund_processed=False,
                status__in=[Registration.Status.CONFIRMED, Registration.Status.WAITING_READY, Registration.Status.READY],
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
            if tournament.status != Tournament.Status.COMPLETED or tournament.is_free_fan_tournament:
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


@admin.action(description="BR winner team: give each listed player 10 Fan Tokens + 50 Coins")
def award_br_winner_team(modeladmin, request, queryset):
    """Credit each verified winner once, with one ledger entry per currency and UID."""
    from apps.social.models import PlayerShopWallet

    awarded_players = 0
    skipped = 0
    for selected in queryset:
        with transaction.atomic():
            tournament = Tournament.objects.select_for_update().get(pk=selected.pk)
            if tournament.mode != Tournament.Mode.BR or tournament.status != Tournament.Status.COMPLETED:
                skipped += 1
                continue
            uids = []
            for raw in (tournament.winner_team_uids or "").replace(",", "\n").splitlines():
                uid = raw.strip()
                if uid and uid not in uids:
                    uids.append(uid)
            if not uids:
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
                wallet.coins += 50
                wallet.save(update_fields=["fan_tokens", "coins", "updated_at"])
                base = f"BR-TEAM-WIN-{tournament.pk}-{uid}"
                TournamentLedgerEntry.objects.create(
                    tournament=tournament, player=registration.player, registration=registration,
                    entry_type=TournamentLedgerEntry.EntryType.REWARD,
                    currency=TournamentLedgerEntry.Currency.FAN_TOKENS, quantity=10,
                    status=TournamentLedgerEntry.Status.COMPLETED, reference=base + "-FAN",
                    description="BR winning team reward: 10 Fan Tokens",
                )
                TournamentLedgerEntry.objects.create(
                    tournament=tournament, player=registration.player, registration=registration,
                    entry_type=TournamentLedgerEntry.EntryType.REWARD,
                    currency=TournamentLedgerEntry.Currency.COINS, quantity=50,
                    status=TournamentLedgerEntry.Status.COMPLETED, reference=base + "-COIN",
                    description="BR winning team reward: 50 Coins",
                )
                awarded_players += 1
    if awarded_players:
        modeladmin.message_user(request, f"{awarded_players} BR winner-team player(s) received 10 Fan Tokens + 50 Coins each.", messages.SUCCESS)
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


@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
    form = TournamentAdminForm
    list_display = (
        "title", "open_tournament_control", "mode", "br_format", "vs_format", "gender_category",
        "entry_fee", "prize_pool", "max_players", "start_time", "status",
        "is_unlimited_br", "auto_reopen", "winner_prize_paid",
    )
    list_filter = ("mode", "br_format", "vs_format", "gender_category", "status", "start_time")
    search_fields = ("title", "description")
    ordering = ("start_time",)
    # Keep tournament setup separate from registrations and kill evidence.
    # Those have their own admin sections so adding/editing a tournament stays manageable.
    inlines = ()
    actions = (cancel_and_refund_tournaments, mark_winner_prizes_paid, award_arena_currency_winner, award_br_winner_team, create_next_round_preserving_history,)
    readonly_fields = (
        "tournament_control_panel", "series_root", "winner_prize_paid",
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

        was_live = previous_status == Tournament.Status.LIVE
        super().save_model(request, obj, form, change)

        # Re-open a fresh no-date 49-player round only after admin marks the current round complete.
        if obj.status == Tournament.Status.COMPLETED and previous_status != Tournament.Status.COMPLETED:
            root = Tournament.objects.get(pk=obj.series_root_id or obj.pk)
            if root.auto_reopen and not root.series_rounds.filter(status=Tournament.Status.UPCOMING).exists():
                next_round_number = root.series_rounds.count() + 2
                Tournament.objects.create(
                    title=f"{root.title} - Round {next_round_number}"[:120],
                    mode=Tournament.Mode.BR, vs_format="", description=root.description,
                    entry_fee=Decimal("0.00") if root.is_free_fan_tournament else root.entry_fee,
                    prize_pool=root.prize_pool, max_players=49,
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
        ("3. Unlimited BR Series — optional", {"description": "Sirf unlimited BR series ke liye ON karein. Har round mein 49 players. Auto start capacity par round shuru karne ke liye hai; Auto reopen agla round khol sakta hai. Normal tournament ho to in options ko OFF rakhein.", "fields": ("is_unlimited_br", "auto_start_at_capacity", "auto_reopen", "series_root")}),
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
            if registration.tournament.is_unlimited_br:
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
        if photo:
            try:
                return format_html('<a href="{}" target="_blank" rel="noopener"><img src="{}" width="88" height="88" style="object-fit:cover;border-radius:10px" alt="Player profile photo"></a>', photo.url, photo.url)
            except (ValueError, OSError):
                return "Photo uploaded but unavailable"
        return "No profile photo"

    @admin.display(description="Player UPI / QR")
    def player_upi_destination(self, obj):
        player = obj.player
        if player.upi_id and player.upi_qr_code:
            try:
                return format_html('UPI ID: {}<br><a href="{}" target="_blank" rel="noopener">Open uploaded UPI QR</a>', player.upi_id, player.upi_qr_code.url)
            except (ValueError, OSError):
                return f"UPI ID: {player.upi_id}"
        if player.upi_id:
            return player.upi_id
        if player.upi_qr_code:
            try:
                return format_html('<a href="{}" target="_blank" rel="noopener">Open uploaded UPI QR</a>', player.upi_qr_code.url)
            except (ValueError, OSError):
                return "UPI QR uploaded but unavailable"
        return "No UPI ID/QR saved in player profile"

    @admin.display(description="Player Wallet Balance")
    def player_wallet_balance(self, obj):
        try:
            return f"₹{obj.player.wallet.balance}"
        except Exception:
            return "Wallet not created"


@admin.action(description="Mark selected BR prizes PAID after completing manual UPI transfer")
def mark_selected_prizes_paid(modeladmin, request, queryset):
    paid = 0
    skipped = 0
    for selected in queryset:
        with transaction.atomic():
            item = KillSubmission.objects.select_for_update().select_related("player", "tournament").get(pk=selected.pk)
            reference = (item.payout_reference or "").strip()
            if (
                item.status != KillSubmission.Status.APPROVED
                or item.tournament.mode != Tournament.Mode.BR
                or item.approved_reward <= 0
                or item.payout_status == KillSubmission.PayoutStatus.PAID
                or len(reference) < 6
                or reference.startswith("KILL-PRIZE-")
            ):
                skipped += 1
                continue
            duplicate = KillSubmission.objects.filter(payout_reference__iexact=reference).exclude(pk=item.pk).exists()
            if duplicate:
                skipped += 1
                continue
            ledger_reference = f"ADMIN-KILL-UPI-{item.pk}"
            if AdminWalletTransaction.objects.filter(reference=ledger_reference).exists():
                skipped += 1
                continue
            admin_wallet, _ = AdminWallet.objects.get_or_create(name="Main Admin Wallet")
            admin_wallet = AdminWallet.objects.select_for_update().get(pk=admin_wallet.pk)
            if admin_wallet.balance < item.approved_reward:
                skipped += 1
                continue
            # Admin must first complete the transfer in their own UPI app and enter its real UTR.
            admin_wallet.balance -= item.approved_reward
            admin_wallet.save(update_fields=["balance", "updated_at"])
            AdminWalletTransaction.objects.create(
                admin_wallet=admin_wallet,
                transaction_type=AdminWalletTransaction.TransactionType.PRIZE,
                amount=item.approved_reward,
                status=AdminWalletTransaction.Status.COMPLETED,
                reference=ledger_reference,
                description=f"Manual UPI BR kill reward; external UTR {reference}; profile {item.player_id}; tournament {item.tournament_id}.",
            )
            item.payout_status = KillSubmission.PayoutStatus.PAID
            item.payout_paid_at = timezone.now()
            item.save(update_fields=["payout_status", "payout_paid_at"])
            paid += 1
    if paid:
        modeladmin.message_user(request, f"{paid} prize(s) marked PAID using manually entered UPI reference(s).", messages.SUCCESS)
    if skipped:
        modeladmin.message_user(request, f"{skipped} item(s) skipped: no approved BR reward, missing/duplicate real UTR, or already paid.", messages.WARNING)


@admin.action(description="Run two-stage AI assessment and credit only strict dual-AI matches")
def run_ai_review_for_selected(modeladmin, request, queryset):
    from .ai_review import analyze_kill_evidence
    from .kill_services import finalize_dual_ai_reward

    reviewed = 0
    rewarded = 0
    manual = 0
    failed = 0
    for selected in queryset.select_related("registration", "tournament", "player"):
        if selected.status != KillSubmission.Status.PENDING:
            failed += 1
            continue
        try:
            result = analyze_kill_evidence(selected)
            proposed = result.get("proposed_kills")
            selected.ai_proposed_kills = proposed
            selected.ai_confidence = (result.get("confidence") or "")[:10]
            selected.ai_uid_matches = result.get("uid_matches")
            selected.ai_review_notes = (result.get("reason") or "")[:2000]
            if proposed is not None and result.get("uid_matches") is True:
                _currency, quantity, _label = reward_for_tournament(selected.tournament, proposed)
                selected.proposed_reward = Decimal(quantity) if proposed >= settings.MINIMUM_VERIFIED_KILLS else Decimal("0.00")
            else:
                selected.proposed_reward = Decimal("0.00")
            selected.save(update_fields=[
                "ai_proposed_kills", "ai_confidence", "ai_uid_matches",
                "ai_review_notes", "proposed_reward",
            ])
            auto_paid, note = finalize_dual_ai_reward(selected, result)
            if auto_paid:
                rewarded += 1
            else:
                selected.refresh_from_db()
                selected.ai_review_notes = (selected.ai_review_notes + "\\n\\nADMIN REVIEW: " + note)[:4000]
                selected.save(update_fields=["ai_review_notes"])
                manual += 1
            reviewed += 1
        except Exception as exc:
            selected.ai_review_notes = f"AI review failed ({exc.__class__.__name__}): {str(exc).strip()[:850]}"
            selected.save(update_fields=["ai_review_notes"])
            failed += 1

    if rewarded:
        modeladmin.message_user(request, f"{rewarded} submission(s) passed both AI models and all website checks; rewards were credited once.", messages.SUCCESS)
    if manual:
        modeladmin.message_user(request, f"{manual} submission(s) need Admin Review because AI agreement or player/evidence checks did not pass.", messages.WARNING)
    if failed:
        modeladmin.message_user(request, f"{failed} submission(s) could not be assessed; check AI Review Notes and review manually.", messages.ERROR)


@admin.register(KillSubmission)
class KillSubmissionAdmin(admin.ModelAdmin):

    def get_queryset(self, request):
        # Ensure the 12-hour media cleanup also runs when staff open the Django
        # admin evidence list/detail page, not only on public tournament pages.
        from .views import cleanup_expired_kill_evidence
        cleanup_expired_kill_evidence()
        return super().get_queryset(request)

    @admin.display(description="Configured AI sources")
    def ai_source_configuration(self, obj):
        import os
        provider = os.getenv("KILL_REVIEW_PROVIDER", "openai").strip().lower()
        openai_model = os.getenv("OPENAI_KILL_REVIEW_MODEL", "gpt-4.1-mini").strip()
        source_model = os.getenv("OLLAMA_KILL_REVIEW_MODEL", "gemma4").strip()
        base_url = os.getenv("KILL_REVIEW_BASE_URL", "").strip()
        return (
            f"Mode: {provider} · OpenAI model: {openai_model} · "
            f"Open-source model: {source_model} · "
            f"Open-source endpoint configured: {'yes' if base_url else 'no'} · "
            f"OpenAI key configured: {'yes' if os.getenv('OPENAI_API_KEY', '').strip() else 'no'} · "
            f"Open-source key configured: {'yes' if os.getenv('KILL_REVIEW_API_KEY', '').strip() else 'no'}"
        )

    # Keep the changelist compact; full evidence, player details, AI notes and payout data
    # are grouped on the dedicated review page opened from the last column.
    list_display = (
        "id", "player", "player_profile_id", "player_phone", "tournament",
        "mode_label", "registered_uid", "free_fire_uid", "status",
        "kills_summary", "ai_confidence", "submitted_at", "open_manual_review",
    )

    @admin.display(description="AI / Approved kills")
    def kills_summary(self, obj):
        if obj.approved_kills is not None:
            return f"Approved: {obj.approved_kills}"
        if obj.ai_proposed_kills is not None:
            return f"AI: {obj.ai_proposed_kills}"
        return "AI not run yet"

    @admin.display(description="Mode")
    def mode_label(self, obj):
        mode = obj.tournament.get_mode_display()
        return f"{mode} ({obj.tournament.vs_format})" if obj.tournament.vs_format else mode

    @admin.display(description="Admin Review")
    def open_manual_review(self, obj):
        url = reverse("tournaments:admin_kill_review") + f"?submission={obj.pk}"
        return format_html('<a class="button" href="{}">Open Review &amp; Confirm</a>', url)

    list_filter = ("status", "payout_status", "ai_confidence", "ai_uid_matches", "tournament__mode", "tournament__gender_category", "tournament", "submitted_at")
    search_fields = ("player__username", "tournament__title", "registered_uid", "free_fire_uid", "payout_reference")
    readonly_fields = (
        "registration", "player", "tournament", "registered_uid", "free_fire_uid",
        "player_profile_id", "player_email", "player_phone", "player_photo",
        "player_upi_id", "payout_qr", "player_wallet_balance",
        "history_video", "history_image_one", "history_image_two",
        "ai_proposed_kills", "ai_confidence", "ai_uid_matches", "ai_review_notes",
        "proposed_reward", "payout_status", "payout_paid_at", "submitted_at", "reviewed_at",
        "ai_source_configuration",
    )
    fieldsets = (
        ("1. Player Contact & Payout Destination", {
            "description": "Prize bhejne se pehle player profile, contact, wallet aur UPI/QR details verify karein.",
            "fields": ("player_profile_id", "player", "player_email", "player_phone", "player_photo", "player_wallet_balance", "player_upi_id", "payout_qr"),
        }),
        ("2. Tournament & UID Match", {
            "description": "Registered UID aur submitted UID compare karein; mismatch ho to approve na karein.",
            "fields": ("registration", "tournament", "registered_uid", "free_fire_uid"),
        }),
        ("2. Uploaded Evidence — open and inspect", {
            "description": "Video aur dono screenshots ko open karke match history, kills aur UID visually check karein.",
            "fields": ("history_video", "history_image_one", "history_image_two"),
        }),
        ("3. AI Assessment Details", {
            "description": "Yahan dono models ke kills, confidence, UID match aur reasons ka combined audit note dikhega. Dual mode mein OpenAI aur open-source model dono ko high-confidence par same kills aur UID match confirm karna hoga; disagreement ya provider failure par automatic Diamonds nahi milenge.",
            "fields": ("ai_proposed_kills", "ai_confidence", "ai_uid_matches", "ai_review_notes", "proposed_reward"),
        }),
        ("4. AI Source Configuration", {
            "description": "Provider keys ko yahan plaintext mein nahi dikhaya jata. Render Environment mein KILL_REVIEW_PROVIDER=dual, OPENAI_API_KEY, OPENAI_KILL_REVIEW_MODEL, KILL_REVIEW_BASE_URL, KILL_REVIEW_API_KEY aur OLLAMA_KILL_REVIEW_MODEL set karein. Model names aur provider status read-only dikhte hain.",
            "fields": ("ai_source_configuration",),
        }),
        ("5. Manual fallback — only unclear cases", {
            "description": "Sirf low-confidence/unclear evidence ko inspect karke approved kills, approved reward, status aur admin notes set karein. ₹10 BR: 5 Diamonds/kill; ₹1 BR: 5 Coins/kill. Approved reward player ke shop wallet mein credit hota hai.",
            "fields": ("approved_kills", "approved_reward", "status", "admin_notes"),
        }),
        ("6. Legacy payout fields", {
            "description": "Purane manual UPI prize records ke liye ye fields rakhe gaye hain. Naye AI kill rewards Diamonds ke roop mein credit hote hain; actual INR withdrawal Currency Withdrawal queue mein handle karein.",
            "fields": ("payout_reference", "payout_status", "payout_paid_at"),
        }),
        ("7. Submission timestamps", {"fields": ("submitted_at", "reviewed_at")}),
    )

    @admin.display(description="Player Email")
    def player_email(self, obj):
        return obj.player.email or "Email not provided"

    @admin.display(description="Player Phone")
    def player_phone(self, obj):
        return obj.player.phone_number or "Phone not provided"

    @admin.display(description="Player Photo")
    def player_photo(self, obj):
        photo = obj.player.profile_photo
        if photo:
            try:
                return format_html('<a href="{}" target="_blank" rel="noopener"><img src="{}" width="88" height="88" style="object-fit:cover;border-radius:10px" alt="Player profile photo"></a>', photo.url, photo.url)
            except (ValueError, OSError):
                return "Photo uploaded but unavailable"
        return "No profile photo"

    @admin.display(description="Player Wallet Balance")
    def player_wallet_balance(self, obj):
        try:
            return f"₹{obj.player.wallet.balance}"
        except Exception:
            return "Wallet not created"

    @admin.display(description="Profile ID", ordering="player__id")
    def player_profile_id(self, obj):
        return obj.player_id

    @admin.display(description="Prize UPI ID", ordering="player__upi_id")
    def player_upi_id(self, obj):
        if (obj.player.upi_id or "").strip():
            return obj.player.upi_id
        if obj.player.upi_qr_code:
            return "UPI ID not entered — use uploaded QR"
        return "Missing — player must add UPI ID or QR in Profile"

    @admin.display(description="UPI QR")
    def payout_qr(self, obj):
        upi_id = (obj.player.upi_id or "").strip()
        if obj.player.upi_qr_code:
            try:
                return format_html(
                    '<a href="{}" target="_blank" rel="noopener"><img src="{}" width="96" height="96" alt="Player uploaded UPI QR for manual prize payout" /></a>',
                    obj.player.upi_qr_code.url,
                    obj.player.upi_qr_code.url,
                )
            except (ValueError, OSError):
                pass
        if not upi_id or "@" not in upi_id:
            return "Player has not provided a usable UPI ID or QR"
        import base64
        import io
        from urllib.parse import urlencode
        import qrcode

        uri = "upi://pay?" + urlencode({
            "pa": upi_id,
            "pn": obj.player.username[:50],
            "cu": "INR",
            "tn": f"FF tournament prize profile {obj.player_id}",
        })
        image = qrcode.make(uri)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return format_html(
            '<img src="data:image/png;base64,{}" width="72" height="72" alt="Player UPI QR" />',
            encoded,
        )

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "proposed_reward":
            kwargs["label"] = "AI Suggested Diamonds"
        elif db_field.name == "approved_reward":
            kwargs["label"] = "Admin-approved Diamonds"
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    # Kill rewards are non-cash Diamonds; cash withdrawals are managed separately.
    actions = (run_ai_review_for_selected,)


@admin.action(description="Retry LIVE email notifications for selected Unlimited Tournaments")
def retry_unlimited_live_notifications(modeladmin, request, queryset):
    from .registration_services import send_unlimited_live_notifications

    attempted = 0
    for tournament in queryset.filter(status=Tournament.Status.LIVE).exclude(live_notification_status="sent"):
        send_unlimited_live_notifications(tournament.pk)
        attempted += 1
    modeladmin.message_user(
        request,
        f"Email retry attempted for {attempted} LIVE Unlimited Tournament(s). Check notification status and email provider delivery.",
        level=messages.INFO,
    )


class UnlimitedTournamentAdminForm(TournamentAdminForm):
    class Meta(TournamentAdminForm.Meta):
        fields = "__all__"

    def clean(self):
        cleaned = super(TournamentAdminForm, self).clean()
        cleaned["mode"] = Tournament.Mode.BR
        cleaned["vs_format"] = ""
        cleaned["gender_category"] = Tournament.GenderCategory.OPEN
        cleaned["is_unlimited_br"] = True
        cleaned["auto_start_at_capacity"] = True
        cleaned["auto_reopen"] = True
        cleaned["max_players"] = 49
        return cleaned


@admin.register(UnlimitedTournament)
class UnlimitedTournamentAdmin(TournamentAdmin):
    """Separate admin menu for the repeating 49-player Unlimited BR series."""

    form = UnlimitedTournamentAdminForm
    exclude = ("start_time",)
    fieldsets = (
        ("Unlimited Tournament Setup", {"description": "No date/time scheduling. Har round mein 49 verified players. Entry ₹10; 49 entries par auto-LIVE. Admin room ID/password LIVE ke baad control panel se send kare.", "fields": ("tournament_control_panel", "title", "description", "entry_fee", "prize_pool", "max_players", "status")}),
        ("Room Credentials", {"fields": ("room_id", "room_password")}),
        ("Unlimited Series & Winner", {"fields": ("is_unlimited_br", "auto_start_at_capacity", "auto_reopen", "series_root", "winner_uid", "winner_payout_destination", "winner_payout_qr", "winner_prize_reference", "winner_prize_paid", "live_notification_sent_at", "live_notification_status")}),
    )

    def get_queryset(self, request):
        return admin.ModelAdmin.get_queryset(self, request).filter(is_unlimited_br=True, is_free_fan_tournament=False)

    def save_model(self, request, obj, form, change):
        obj.is_unlimited_br = True
        obj.is_free_fan_tournament = False
        obj.auto_start_at_capacity = True
        obj.auto_reopen = True
        obj.mode = Tournament.Mode.BR
        obj.vs_format = ""
        obj.max_players = 49
        obj.entry_fee = Decimal("10.00")
        if not change:
            obj.status = Tournament.Status.UPCOMING
            if not obj.start_time or obj.start_time <= timezone.now():
                obj.start_time = timezone.now() + timedelta(minutes=10)
        super().save_model(request, obj, form, change)

    @admin.display(description="Players", ordering="start_time")
    def confirmed_players_count_display(self, obj):
        return f"{obj.paid_players_count}/49"

    list_filter = ("status", "auto_reopen", "live_notification_status")
    list_display = (
        "title", "entry_fee", "confirmed_players_count_display",
        "status", "auto_reopen", "live_notification_status",
    )
    search_fields = ("title", "description")
    ordering = ("-created_at",)
    actions = (cancel_and_refund_tournaments, mark_winner_prizes_paid, retry_unlimited_live_notifications)
    readonly_fields = (
        "tournament_control_panel", "series_root", "winner_prize_paid",
        "kill_prize_distributed", "kill_prize_pool", "kill_prize_reference",
        "live_notification_sent_at", "live_notification_status",
        "winner_payout_destination", "winner_payout_qr",
    )


@admin.action(description="Award the configured winner Coins (free tournament only)")
def award_free_tournament_winner_coins(modeladmin, request, queryset):
    awarded = 0
    skipped = 0
    with transaction.atomic():
        for selected in queryset.select_for_update():
            tournament = Tournament.objects.select_for_update().get(pk=selected.pk)
            if not tournament.is_free_fan_tournament or tournament.status != Tournament.Status.COMPLETED or tournament.free_winner_coins_awarded:
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
            winner = winners.first()
            reference = f"FREE-WIN-COINS-{tournament.pk}"
            if TournamentLedgerEntry.objects.filter(reference=reference).exists():
                tournament.free_winner_coins_awarded = True
                tournament.save(update_fields=["free_winner_coins_awarded", "updated_at"])
                skipped += 1
                continue
            from apps.social.models import PlayerShopWallet
            wallet, _ = PlayerShopWallet.objects.get_or_create(user=winner.player)
            wallet = PlayerShopWallet.objects.select_for_update().get(pk=wallet.pk)
            quantity = int(tournament.winner_coins_prize or 20)
            wallet.coins += quantity
            wallet.save(update_fields=["coins", "updated_at"])
            TournamentLedgerEntry.objects.create(
                tournament=tournament,
                player=winner.player,
                registration=winners.first(),
                entry_type=TournamentLedgerEntry.EntryType.REWARD,
                currency=TournamentLedgerEntry.Currency.COINS,
                quantity=quantity,
                amount_inr=Decimal("0.00"),
                status=TournamentLedgerEntry.Status.COMPLETED,
                reference=reference,
                description=f"Free Fan Tournament winner prize: {quantity} Coins",
            )
            tournament.free_winner_coins_awarded = True
            tournament.save(update_fields=["free_winner_coins_awarded", "updated_at"])
            awarded += 1
    if awarded:
        modeladmin.message_user(request, f"{awarded} free tournament winner prize(s) awarded as Coins.", messages.SUCCESS)
    if skipped:
        modeladmin.message_user(request, f"{skipped} skipped: tournament must be completed, winner UID must uniquely match a verified registration, and prize must not already be awarded.", messages.WARNING)


class FreeFanTournamentAdminForm(TournamentAdminForm):
    class Meta(TournamentAdminForm.Meta):
        fields = "__all__"

    def clean(self):
        # Keep the dedicated form date-free and avoid asking admins to configure hidden BR fields.
        cleaned = super(TournamentAdminForm, self).clean()
        cleaned["mode"] = Tournament.Mode.BR
        cleaned["vs_format"] = ""
        cleaned["gender_category"] = Tournament.GenderCategory.OPEN
        cleaned["is_unlimited_br"] = True
        cleaned["auto_start_at_capacity"] = True
        cleaned["auto_reopen"] = True
        cleaned["max_players"] = 49
        return cleaned


@admin.register(FreeFanTournament)
class FreeFanTournamentAdmin(TournamentAdmin):
    """Separate admin controls for the recurring free 49-player fan tournament."""

    form = FreeFanTournamentAdminForm
    exclude = ("start_time",)
    list_display = ("title", "confirmed_players_count_display", "status", "winner_coins_prize", "free_winner_coins_awarded", "live_notification_status")
    list_filter = ("status", "free_winner_coins_awarded", "live_notification_status")
    actions = (cancel_and_refund_tournaments, award_free_tournament_winner_coins)
    fieldsets = (
        ("Free Fan Tournament Setup", {"description": "Yeh alag, no-date free BR series hai. Entry fee zero, capacity 49, 2 verified kills par 1 Fan Token, winner ko 20 Coins. 49 verified players par automatic LIVE.", "fields": ("tournament_control_panel", "title", "description", "winner_coins_prize", "max_players", "status")}),
        ("Admin Room Credentials", {"description": "Room ID aur password sirf admin yahan set kare. LIVE round mein credentials eligible players ko private player-room page par milenge.", "fields": ("room_id", "room_password")}),
        ("Series & Winner", {"fields": ("is_free_fan_tournament", "is_unlimited_br", "auto_start_at_capacity", "auto_reopen", "series_root", "winner_uid", "free_winner_coins_awarded", "live_notification_sent_at", "live_notification_status")}),
    )
    readonly_fields = ("tournament_control_panel", "series_root", "winner_coins_prize", "free_winner_coins_awarded", "live_notification_sent_at", "live_notification_status")
    ordering = ("-created_at",)

    def get_queryset(self, request):
        return admin.ModelAdmin.get_queryset(self, request).filter(is_free_fan_tournament=True)

    def confirmed_players_count_display(self, obj):
        return f"{obj.confirmed_players_count}/49"
    confirmed_players_count_display.short_description = "Players"

    def save_model(self, request, obj, form, change):
        obj.is_free_fan_tournament = True
        obj.is_unlimited_br = True
        obj.auto_start_at_capacity = True
        obj.auto_reopen = True
        obj.mode = Tournament.Mode.BR
        obj.vs_format = ""
        obj.gender_category = Tournament.GenderCategory.OPEN
        obj.max_players = 49
        obj.entry_fee = Decimal("0.00")
        obj.winner_coins_prize = 20
        if not obj.start_time or obj.start_time <= timezone.now():
            obj.start_time = timezone.now() + timedelta(minutes=10)
        if not change:
            obj.status = Tournament.Status.UPCOMING
        super().save_model(request, obj, form, change)


@admin.register(TournamentLedgerEntry)
class TournamentLedgerEntryAdmin(admin.ModelAdmin):
    list_display = ("created_at", "tournament", "player", "entry_type", "currency", "quantity", "amount_inr", "status", "reference")
    list_filter = ("tournament", "entry_type", "currency", "status", "created_at")
    search_fields = ("tournament__title", "player__username", "reference", "description")
    date_hierarchy = "created_at"
    list_select_related = ("tournament", "player", "registration")
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)
