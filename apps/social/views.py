from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from datetime import timedelta
import random
from django.views.decorators.http import require_POST

from .models import Follow, FriendRequest, UserBlock, UserReport, PhotoPost, FFTickSubscription, PlayerShopWallet, ShopPaymentRequest, CurrencyWithdrawalRequest, DailySpin, FanTokenAward
from apps.accounts.forms import CurrencyWithdrawalRequestForm

User = get_user_model()


def _blocked_either_way(first, second):
    return UserBlock.objects.filter(
        Q(blocker=first, blocked=second) | Q(blocker=second, blocked=first)
    ).exists()


def _are_friends(first, second):
    # Friendship exists only while both players follow each other.
    return Follow.objects.filter(follower=first, following=second).exists() and Follow.objects.filter(
        follower=second, following=first
    ).exists()


@login_required
def friends_home(request):
    user = request.user
    search_query = request.GET.get("q", "").strip()
    search_results = []
    blocked_ids = set(
        UserBlock.objects.filter(Q(blocker=user) | Q(blocked=user)).values_list(
            "blocker_id", flat=True
        )
    ) | set(
        UserBlock.objects.filter(Q(blocker=user) | Q(blocked=user)).values_list(
            "blocked_id", flat=True
        )
    )
    if search_query:
        users = User.objects.exclude(pk=user.pk).exclude(pk__in=blocked_ids)
        if search_query.upper().startswith("FF-"):
            numeric_id = search_query[3:]
            users = users.filter(pk=int(numeric_id)) if numeric_id.isdigit() else users.none()
        elif search_query.isdigit():
            users = users.filter(pk=int(search_query))
        else:
            # Allow partial username searches, not just exact matches.
            users = users.filter(username__icontains=search_query)
        for candidate in users.order_by("username")[:10]:
            search_results.append({
                "user": candidate,
                "is_friend": _are_friends(user, candidate),
                "outgoing": FriendRequest.objects.filter(
                    requester=user, recipient=candidate, status=FriendRequest.Status.PENDING
                ).exists(),
                "incoming": FriendRequest.objects.filter(
                    requester=candidate, recipient=user, status=FriendRequest.Status.PENDING
                ).exists(),
                "is_following": Follow.objects.filter(follower=user, following=candidate).exists(),
            })

    # Suggestions are real registered accounts only. Hide self, blocked accounts,
    # and players the current user already follows.
    following_ids = set(
        Follow.objects.filter(follower=user).values_list("following_id", flat=True)
    )
    suggestions = User.objects.exclude(pk=user.pk).exclude(
        pk__in=blocked_ids | following_ids
    ).order_by("-date_joined", "username")[:8]

    incoming = FriendRequest.objects.filter(
        recipient=user, status=FriendRequest.Status.PENDING
    ).select_related("requester")
    outgoing = FriendRequest.objects.filter(
        requester=user, status=FriendRequest.Status.PENDING
    ).select_related("recipient")
    following_ids = set(Follow.objects.filter(follower=user).values_list("following_id", flat=True))
    follower_ids = set(Follow.objects.filter(following=user).values_list("follower_id", flat=True))
    mutual_ids = following_ids.intersection(follower_ids)
    friends = [
        candidate for candidate in User.objects.filter(pk__in=mutual_ids)
        if not _blocked_either_way(user, candidate)
    ]

    blocked_users = UserBlock.objects.filter(blocker=user).select_related("blocked")
    return render(request, "social/friends.html", {
        "search_query": search_query,
        "search_results": search_results,
        "suggestions": suggestions,
        "incoming_requests": incoming,
        "outgoing_requests": outgoing,
        "friends": friends,
        "blocked_users": blocked_users,
    })


@require_POST
@login_required
def send_friend_request(request, user_id):
    target = get_object_or_404(User, pk=user_id)
    if target.pk == request.user.pk:
        messages.error(request, "Aap khud ko friend nahi bana sakte.")
        return redirect("social:home")
    if _blocked_either_way(request.user, target):
        messages.error(request, "Block hone ki wajah se request nahi bhej sakte.")
        return redirect("social:home")
    if _are_friends(request.user, target):
        messages.info(request, "Ye player pehle se aapka friend hai.")
        return redirect("social:home")

    with transaction.atomic():
        reverse_request = FriendRequest.objects.select_for_update().filter(
            requester=target, recipient=request.user
        ).first()
        if reverse_request and reverse_request.status == FriendRequest.Status.PENDING:
            reverse_request.status = FriendRequest.Status.ACCEPTED
            reverse_request.save(update_fields=["status", "updated_at"])
            messages.success(request, f"{target.username} ke saath friendship accept ho gayi.")
            return redirect("social:home")
        existing = FriendRequest.objects.filter(requester=request.user, recipient=target).first()
        if existing and existing.status == FriendRequest.Status.PENDING:
            messages.info(request, "Friend request pehle hi bheji ja chuki hai.")
        elif existing:
            existing.status = FriendRequest.Status.PENDING
            existing.save(update_fields=["status", "updated_at"])
            messages.success(request, "Friend request dobara bhej di gayi.")
        else:
            try:
                FriendRequest.objects.create(requester=request.user, recipient=target)
                messages.success(request, "Friend request bhej di gayi.")
            except IntegrityError:
                messages.info(request, "Friend request already exists.")
    return redirect("social:home")


@require_POST
@login_required
def handle_friend_request(request, request_id, action):
    friend_request = get_object_or_404(FriendRequest, pk=request_id, recipient=request.user)
    if friend_request.status != FriendRequest.Status.PENDING:
        messages.info(request, "Ye request ab pending nahi hai.")
    elif _blocked_either_way(request.user, friend_request.requester):
        friend_request.status = FriendRequest.Status.REJECTED
        friend_request.save(update_fields=["status", "updated_at"])
        messages.error(request, "Blocked player ki request accept nahi ho sakti.")
    elif action == "accept":
        friend_request.status = FriendRequest.Status.ACCEPTED
        friend_request.save(update_fields=["status", "updated_at"])
        messages.success(request, f"{friend_request.requester.username} ab aapka friend hai.")
    elif action == "reject":
        friend_request.status = FriendRequest.Status.REJECTED
        friend_request.save(update_fields=["status", "updated_at"])
        messages.success(request, "Friend request reject kar di.")
    else:
        messages.error(request, "Invalid action.")
    return redirect("social:home")


@require_POST
@login_required
def cancel_friend_request(request, request_id):
    friend_request = get_object_or_404(
        FriendRequest, pk=request_id, requester=request.user, status=FriendRequest.Status.PENDING
    )
    friend_request.delete()
    messages.success(request, "Sent friend request cancel kar di.")
    return redirect("social:home")


@require_POST
@login_required
def remove_friend(request, user_id):
    target = get_object_or_404(User, pk=user_id)
    Follow.objects.filter(
        Q(follower=request.user, following=target) | Q(follower=target, following=request.user)
    ).delete()
    FriendRequest.objects.filter(
        Q(requester=request.user, recipient=target) | Q(requester=target, recipient=request.user),
        status=FriendRequest.Status.ACCEPTED,
    ).update(status=FriendRequest.Status.REJECTED)
    messages.success(request, f"{target.username} ko friends list se remove kar diya.")
    return redirect("social:home")


@require_POST
@login_required
def block_user(request, user_id):
    target = get_object_or_404(User, pk=user_id)
    if target.pk == request.user.pk:
        messages.error(request, "Aap khud ko block nahi kar sakte.")
    else:
        UserBlock.objects.get_or_create(blocker=request.user, blocked=target)
        FriendRequest.objects.filter(
            Q(requester=request.user, recipient=target) | Q(requester=target, recipient=request.user),
            status=FriendRequest.Status.ACCEPTED,
        ).update(status=FriendRequest.Status.REJECTED)
        messages.success(request, f"{target.username} block kar diya. Chat band rahegi.")
    return redirect("social:home")


@require_POST
@login_required
def unblock_user(request, user_id):
    target = get_object_or_404(User, pk=user_id)
    UserBlock.objects.filter(blocker=request.user, blocked=target).delete()
    messages.success(request, f"{target.username} ko unblock kar diya.")
    return redirect("social:home")


@login_required
def report_user(request, user_id):
    target = get_object_or_404(User, pk=user_id)
    if target.pk == request.user.pk:
        messages.error(request, "Aap apne account ko report nahi kar sakte.")
        return redirect("social:home")
    if request.method == "POST":
        reason = request.POST.get("reason", "")
        details = request.POST.get("details", "").strip()[:1000]
        valid_reasons = {value for value, label in UserReport.Reason.choices}
        if reason not in valid_reasons:
            messages.error(request, "Report reason select karo.")
        else:
            UserReport.objects.create(
                reporter=request.user, reported_user=target, reason=reason, details=details
            )
            messages.success(request, "Report admin team ko bhej di gayi.")
            return redirect("social:home")
    return render(request, "social/report_user.html", {"target": target, "reasons": UserReport.Reason.choices})


from .models import Follow


@login_required
@require_POST
@transaction.atomic
def toggle_follow(request, user_id):
    target = get_object_or_404(User, pk=user_id)
    if target.pk == request.user.pk:
        messages.error(request, "Aap khud ko follow nahi kar sakte.")
    elif _blocked_either_way(request.user, target):
        messages.error(request, "Block hone ki wajah se follow nahi kar sakte.")
    else:
        relation = Follow.objects.filter(follower=request.user, following=target).first()
        if relation:
            relation.delete()
            messages.success(request, f"Ab aap {target.username} ko follow nahi karte.")
        else:
            Follow.objects.create(follower=request.user, following=target)
            # Grant one Fan Token at each new 10-follower milestone, exactly once.
            follower_count = Follow.objects.filter(following=target).count()
            awarded = 0
            for milestone in range(10, (follower_count // 10) * 10 + 1, 10):
                _, created = FanTokenAward.objects.get_or_create(
                    user=target, follower_milestone=milestone,
                    defaults={"quantity": 1},
                )
                if created:
                    wallet, _ = PlayerShopWallet.objects.get_or_create(user=target)
                    wallet = PlayerShopWallet.objects.select_for_update().get(pk=wallet.pk)
                    wallet.fan_tokens += 1
                    wallet.save(update_fields=["fan_tokens", "updated_at"])
                    awarded += 1
            if awarded:
                messages.success(request, f"Aap ab {target.username} ko follow kar rahe hain. Unhe {awarded} Fan Token mila — har 10 followers par 1 token!")
            else:
                messages.success(request, f"Aap ab {target.username} ko follow kar rahe hain.")
    return redirect(request.POST.get("next") or "social:home")


@login_required
def player_profile(request, user_id):
    """Public player card; never expose private contact, payment, or UID fields."""
    target = get_object_or_404(User, pk=user_id)
    if target.pk == request.user.pk:
        return redirect("accounts:profile")
    if _blocked_either_way(request.user, target):
        messages.info(request, "Ye player profile privacy settings ki wajah se available nahi hai.")
        return redirect("social:home")
    followers_count = Follow.objects.filter(following=target).count()
    following_count = Follow.objects.filter(follower=target).count()
    is_following = Follow.objects.filter(follower=request.user, following=target).exists()
    if getattr(target, "profile_visibility", "public") == "private" and not is_following:
        messages.info(request, "Ye private profile hai. Pehle player ko follow karein, phir profile dekh sakte hain.")
        return redirect("social:home")
    is_friend = _are_friends(request.user, target)
    return render(request, "social/player_profile.html", {
        "player": target, "followers_count": followers_count,
        "following_count": following_count, "is_following": is_following,
        "is_friend": is_friend,
        "posts": PhotoPost.objects.filter(author=target, is_hidden=False)[:12],
        "has_ff_tick": FFTickSubscription.objects.filter(user=target, status=FFTickSubscription.Status.ACTIVE, expires_at__gt=__import__("django.utils.timezone", fromlist=["now"]).now()).exists(),
    })

@login_required
def follow_lists(request, list_type="followers"):
    if list_type == "following":
        links = Follow.objects.filter(follower=request.user).select_related("following")
        people = [link.following for link in links]
        title = "Following"
    else:
        links = Follow.objects.filter(following=request.user).select_related("follower")
        people = [link.follower for link in links]
        title = "Followers"
    return render(request, "social/follows.html", {"people": people, "title": title, "list_type": list_type})


@login_required
def community_feed(request):
    from django.utils import timezone
    if request.method == "POST":
        photo = request.FILES.get("photo")
        caption = request.POST.get("caption", "").strip()[:180]
        if not photo:
            messages.error(request, "Photo upload karna zaroori hai.")
        elif photo.size > 5 * 1024 * 1024:
            messages.error(request, "Photo 5 MB se chhoti honi chahiye.")
        elif getattr(photo, "content_type", "") not in ("image/jpeg", "image/png", "image/webp"):
            messages.error(request, "Sirf JPG, PNG ya WebP photo upload karein.")
        else:
            PhotoPost.objects.create(author=request.user, photo=photo, caption=caption)
            messages.success(request, "Photo post ho gayi!")
            return redirect("social:feed")
    posts = PhotoPost.objects.filter(is_hidden=False).select_related("author")[:60]
    return render(request, "social/feed.html", {"posts": posts})


def _shop_payment_qr_data_uri():
    """Build a QR for the shop's UPI ID; it does not confirm or verify a payment."""
    import base64
    from io import BytesIO
    import qrcode

    upi_uri = "upi://pay?pa=6232481135%40fam&pn=Ravibaghel&cu=INR"
    image = qrcode.make(upi_uri)
    output = BytesIO()
    image.save(output, format="PNG")
    encoded = base64.b64encode(output.getvalue()).decode("ascii")
    return "data:image/png;base64," + encoded


@login_required
def ff_tick_view(request):
    from django.utils import timezone
    current = FFTickSubscription.objects.filter(
        user=request.user, status=FFTickSubscription.Status.ACTIVE, expires_at__gt=timezone.now()
    ).first()
    latest = FFTickSubscription.objects.filter(user=request.user).first()
    if request.method == "POST":
        reference = request.POST.get("payment_reference", "").strip()[:100]
        screenshot = request.FILES.get("payment_screenshot")
        if not reference:
            messages.error(request, "Payment ke baad real UPI UTR/reference bharein.")
        elif not screenshot:
            messages.error(request, "Payment screenshot upload karna zaroori hai.")
        elif screenshot.size > 5 * 1024 * 1024 or getattr(screenshot, "content_type", "") not in ("image/jpeg", "image/png", "image/webp"):
            messages.error(request, "Screenshot JPG/PNG/WebP ho aur 5 MB se chhota ho.")
        elif FFTickSubscription.objects.filter(payment_reference=reference).exclude(status=FFTickSubscription.Status.REJECTED).exists():
            messages.error(request, "Ye payment reference pehle submit ho chuka hai.")
        else:
            FFTickSubscription.objects.create(user=request.user, amount=100, duration_months=3, payment_reference=reference, payment_screenshot=screenshot)
            messages.success(request, "FF Tick request admin ko bhej di. Payment verify hone ke baad hi badge active hoga.")
            return redirect("social:ff_tick")
    return render(request, "social/ff_tick.html", {"current": current, "latest": latest, "payment_qr_data_uri": _shop_payment_qr_data_uri()})


@login_required
def shop_view(request):
    from decimal import Decimal
    from django.utils import timezone
    from django.db import transaction
    from django.db.models import F
    wallet, _ = PlayerShopWallet.objects.get_or_create(user=request.user)
    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "buy":
            product = request.POST.get("product")
            try:
                quantity = int(request.POST.get("quantity", "0"))
            except (TypeError, ValueError):
                quantity = 0
            # Fixed packs only. Diamonds and coins are virtual, non-cash shop items.
            packs = {("diamonds", 10): Decimal("10.00"), ("diamonds", 50): Decimal("50.00"),
                     ("diamonds", 100): Decimal("100.00"), ("diamonds", 500): Decimal("500.00"),
                     ("coins", 100): Decimal("10.00"), ("coins", 500): Decimal("50.00"),
                     ("coins", 1000): Decimal("100.00")}
            amount = packs.get((product, quantity))
            reference = request.POST.get("payment_reference", "").strip()[:100]
            screenshot = request.FILES.get("payment_screenshot")
            if amount is None:
                messages.error(request, "Shop se valid fixed pack select karein.")
            elif not reference or not screenshot:
                messages.error(request, "Actual UPI UTR aur payment screenshot dono zaroori hain.")
            elif screenshot.size > 5 * 1024 * 1024 or getattr(screenshot, "content_type", "") not in ("image/jpeg", "image/png", "image/webp"):
                messages.error(request, "Payment screenshot JPG/PNG/WebP ho aur 5 MB se chhota ho.")
            elif ShopPaymentRequest.objects.filter(payment_reference__iexact=reference).exists():
                messages.error(request, "Ye payment reference pehle submit ho chuka hai.")
            else:
                ShopPaymentRequest.objects.create(user=request.user, product=product, quantity=quantity, amount=amount, payment_reference=reference, payment_screenshot=screenshot)
                messages.success(request, "Shop payment request admin verification ke liye bhej di gayi. Approval ke baad items balance mein aayenge.")
                return redirect("social:shop")

    wallet.refresh_from_db()
    return render(request, "social/shop.html", {
        "shop_wallet": wallet,
        "payment_requests": ShopPaymentRequest.objects.filter(user=request.user)[:10],
        "payment_qr_data_uri": _shop_payment_qr_data_uri(),
    })


@login_required
@require_POST
def daily_spin(request):
    """One database-backed free spin per 24 hours; rewards are small and non-cash."""
    with transaction.atomic():
        wallet, _ = PlayerShopWallet.objects.get_or_create(user=request.user)
        wallet = PlayerShopWallet.objects.select_for_update().get(pk=wallet.pk)
        last_spin = DailySpin.objects.filter(user=request.user).order_by("-spun_at").first()
        now = timezone.now()
        if last_spin and now < last_spin.spun_at + timedelta(hours=24):
            available_at = last_spin.spun_at + timedelta(hours=24)
            wait_seconds = max(0, int((available_at - now).total_seconds()))
            hours, remainder = divmod(wait_seconds, 3600)
            minutes = remainder // 60
            messages.info(request, f"Daily Spin already used. Next spin in about {hours}h {minutes}m.")
            return redirect("accounts:wallet")

        # Only the requested small rewards are possible.
        if random.choice((True, False)):
            currency = DailySpin.Currency.DIAMONDS
            quantity = random.choice((1, 2))
            wallet.diamonds += quantity
        else:
            currency = DailySpin.Currency.COINS
            quantity = random.choice((5, 10, 15, 20, 25))
            wallet.coins += quantity
        wallet.save(update_fields=("diamonds", "coins", "updated_at"))
        DailySpin.objects.create(user=request.user, currency=currency, quantity=quantity)

    messages.success(request, f"🎉 Daily Spin reward: +{quantity} {currency.title()}! Come back after 24 hours for another spin.")
    return redirect("accounts:wallet")



@login_required
def currency_withdrawal_view(request):
    """Submit a manual-review request to convert shop currency to INR."""
    from decimal import Decimal

    wallet, _ = PlayerShopWallet.objects.get_or_create(user=request.user)
    if request.method == "POST":
        form = CurrencyWithdrawalRequestForm(request.POST, request.FILES)
        if form.is_valid():
            currency = form.cleaned_data["currency"]
            quantity = form.cleaned_data["quantity"]
            upi_id = form.cleaned_data["upi_id"]
            # Rates match the current shop packs: 1 diamond = ₹1; 10 coins = ₹1.
            amount = Decimal(quantity) if currency == "diamonds" else Decimal(quantity) / Decimal("10")
            if amount < Decimal("10.00"):
                form.add_error("quantity", "Minimum withdrawal ₹10 hai: 10 diamonds ya 100 coins.")
            else:
                with transaction.atomic():
                    wallet = PlayerShopWallet.objects.select_for_update().get(pk=wallet.pk)
                    pending = CurrencyWithdrawalRequest.objects.filter(
                        user=request.user, status=CurrencyWithdrawalRequest.Status.PENDING
                    ).exists()
                    if pending:
                        form.add_error(None, "Aapki ek currency withdrawal request pehle se pending hai.")
                    elif currency == "diamonds" and wallet.diamonds < quantity:
                        form.add_error("quantity", "Aapke paas itne diamonds nahi hain.")
                    elif currency == "coins" and wallet.coins < quantity:
                        form.add_error("quantity", "Aapke paas itne coins nahi hain.")
                    else:
                        CurrencyWithdrawalRequest.objects.create(
                            user=request.user,
                            currency=currency,
                            quantity=quantity,
                            amount_inr=amount,
                            upi_id=upi_id,
                        )
                        if currency == "diamonds":
                            wallet.diamonds -= quantity
                            wallet.save(update_fields=("diamonds", "updated_at"))
                        else:
                            wallet.coins -= quantity
                            wallet.save(update_fields=("coins", "updated_at"))
                        messages.success(
                            request,
                            f"₹{amount:.2f} ki withdrawal request admin review ke liye bhej di. Actual UPI transfer aur verification ke baad hi payout complete hoga."
                        )
                        return redirect("social:currency_withdrawal")
    else:
        form = CurrencyWithdrawalRequestForm(initial={"upi_id": request.user.upi_id})
    requests = CurrencyWithdrawalRequest.objects.filter(user=request.user)[:20]
    return render(request, "social/currency_withdrawal.html", {
        "form": form,
        "shop_wallet": wallet,
        "withdrawal_requests": requests,
    })
