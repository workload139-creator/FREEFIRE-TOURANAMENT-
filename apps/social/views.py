from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Follow, FriendRequest, UserBlock, UserReport

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
            # Accepted friendship must create the mutual follows required by chat.
            Follow.objects.get_or_create(follower=request.user, following=target)
            Follow.objects.get_or_create(follower=target, following=request.user)
            messages.success(request, f"{target.username} ke saath friendship accept ho gayi. Ab aap chat kar sakte hain.")
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
        with transaction.atomic():
            friend_request.status = FriendRequest.Status.ACCEPTED
            friend_request.save(update_fields=["status", "updated_at"])
            # Chat access is based on mutual follows; create both directions on accept.
            Follow.objects.get_or_create(follower=request.user, following=friend_request.requester)
            Follow.objects.get_or_create(follower=friend_request.requester, following=request.user)
        messages.success(request, f"{friend_request.requester.username} ab aapka friend hai. Ab aap chat kar sakte hain.")
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
            messages.success(request, f"Aap ab {target.username} ko follow kar rahe hain.")
    return redirect(request.POST.get("next") or "social:home")


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
