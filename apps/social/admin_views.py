from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .models import InstagramPromotionOrder


@staff_member_required
def instagram_promotion_admin(request):
    orders = InstagramPromotionOrder.objects.select_related("user").order_by("-created_at")
    status = request.GET.get("status", "").strip()
    valid_statuses = {choice for choice, _label in InstagramPromotionOrder.Status.choices}
    if status in valid_statuses:
        orders = orders.filter(status=status)

    counts = {
        row["status"]: row["total"]
        for row in InstagramPromotionOrder.objects.values("status").annotate(total=Count("id"))
    }
    return render(request, "admin/social/instagram_promotions.html", {
        "orders": orders,
        "selected_status": status,
        "status_choices": InstagramPromotionOrder.Status.choices,
        "counts": counts,
        "total_orders": sum(counts.values()),
        **({"title": "Instagram Promotion Requests"} if True else {}),
    })


@staff_member_required
@require_POST
def update_instagram_promotion_admin(request, order_id):
    order = InstagramPromotionOrder.objects.filter(pk=order_id).first()
    if order is None:
        messages.error(request, "Instagram promotion request nahi mili.")
        return redirect("instagram_promotion_admin")

    new_status = request.POST.get("status", "").strip()
    valid_statuses = {choice for choice, _label in InstagramPromotionOrder.Status.choices}
    if new_status not in valid_statuses:
        messages.error(request, "Invalid status.")
        return redirect("instagram_promotion_admin")

    order.status = new_status
    order.admin_note = request.POST.get("admin_note", "").strip()[:500]
    order.save(update_fields=("status", "admin_note", "updated_at"))
    messages.success(request, f"Request #{order.pk} update ho gayi.")
    return redirect("instagram_promotion_admin")
