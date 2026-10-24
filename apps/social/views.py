from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import FriendRequest, UserBlock, UserReport

User = get_user_model()


def _blocked_either_way(first, second):
    return UserBlock.objects.filter(
        Q(blocker=first, blocked=second) | Q(blocker=second, blocked=first)
    ).exists()


def _are_friends(first, second):
    return FriendRequest.objects.filter(
        Q(requester=first, recipient=second) | Q(requester=second, recipient=first),
        status=FriendRequest.Status.ACCEPTED,
    ).exists()


@login_required
def friends_home(request):
    user = request.user
    search_query = request.GET.get("q", "").strip()
    search_results = []
    if search_query:
        users = User.objects.exclude(pk=user.pk)
        if search_query.upper().startswith("FF-"):
            numeric_id = search_query[3:]
            users = users.filter(pk=int(numeric_id)) if numeric_id.isdigit() else users.none()
        elif search_query.isdigit():
            users = users.filter(pk=int(search_query))
        else:
            users = users.filter(username__iexact=search_query)
        for candidate in users[:10]:
            if not _blocked_either_way(user, candidate):
                search_results.append({
                    "user": candidate,
                    "is_friend": _are_friends(user, candidate),
                    "outgoing": FriendRequest.objects.filter(
                        requester=user, recipient=candidate, status=FriendRequest.Status.PENDING
                    ).exists(),
                    "incoming": FriendRequest.objects.filter(
                        requester=candidate, recipient=user, status=FriendRequest.Status.PENDING
                    ).exists(),
                })

    incoming = FriendRequest.objects.filter(
        recipient=user, status=FriendRequest.Status.PENDING
    ).select_related("requester")
    outgoing = FriendRequest.objects.filter(
        requester=user, status=FriendRequest.Status.PENDING
    ).select_related("recipient")
    accepted = FriendRequest.objects.filter(status=FriendRequest.Status.ACCEPTED).filter(
        Q(requester=user) | Q(recipient=user)
    ).select_related("requester", "recipient")

    friends = []
    for friendship in accepted:
        friend = friendship.recipient if friendship.requester_id == user.pk else friendship.requester
        if not _blocked_either_way(user, friend):
            friends.append(friend)

    blocked_users = UserBlock.objects.filter(blocker=user).select_related("blocked")
    return render(request, "social/friends.html", {
        "search_query": search_query,
        "search_results": search_results,
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
def remove_friend(request, user_id):
    target = get_object_or_404(User, pk=user_id)
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
