from django.apps import apps
from django.db.models.signals import post_save


def _track(sender, instance, created, **kwargs):
    from .activity_monitor import record_player_activity
    record_player_activity(instance, created=created)


def connect_activity_signals():
    watched = (
        ("accounts", "User"), ("accounts", "Wallet"),
        ("accounts", "WalletTransaction"), ("accounts", "DepositRequest"),
        ("accounts", "WithdrawalRequest"),
        ("social", "PlayerShopWallet"), ("social", "PlayerShopWalletTransaction"),
        ("social", "ShopPaymentRequest"), ("social", "CurrencyWithdrawalRequest"),
        ("social", "DailySpin"), ("social", "CurrencyGift"),
        ("social", "Follow"), ("social", "FriendRequest"),
        ("social", "PhotoPost"), ("social", "UserReport"),
        ("tournaments", "Registration"), ("tournaments", "TournamentLedgerEntry"),
        ("tournaments", "KillSubmission"),
    )
    for app_label, model_name in watched:
        try:
            model = apps.get_model(app_label, model_name)
            post_save.connect(
                _track, sender=model,
                dispatch_uid=f"ff_player_activity_ai_{app_label}_{model_name}",
                weak=False,
            )
        except LookupError:
            continue
