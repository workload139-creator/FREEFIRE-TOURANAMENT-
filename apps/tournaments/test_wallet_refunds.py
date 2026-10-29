from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Wallet, WalletTransaction
from .models import Registration, Tournament
from .services import cancel_tournament_and_refund, mark_not_playing_and_refund


class VerifiedEntryWalletRefundTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="refund-player",
            password="test-password-123",
        )
        self.tournament = Tournament.objects.create(
            title="Refund Test Tournament",
            start_time=timezone.now() + timedelta(hours=2),
            entry_fee=Decimal("50.00"),
            status=Tournament.Status.UPCOMING,
        )

    def make_registration(self, **overrides):
        values = {
            "tournament": self.tournament,
            "player": self.user,
            "free_fire_uid": "123456789",
            "entry_fee_paid": Decimal("50.00"),
            "payment_verified": True,
            "payment_method": "upi",
            "payment_reference": "UTR-TEST-123",
            "status": Registration.Status.WAITING_READY,
            "ready_deadline": timezone.now() - timedelta(minutes=1),
        }
        values.update(overrides)
        return Registration.objects.create(**values)

    def test_missed_ready_confirmation_credits_verified_upi_payment_to_wallet_once(self):
        registration = self.make_registration()

        changed, message = mark_not_playing_and_refund(registration.pk)

        self.assertTrue(changed, message)
        registration.refresh_from_db()
        wallet = Wallet.objects.get(user=self.user)
        self.assertEqual(wallet.balance, Decimal("50.00"))
        self.assertEqual(
            WalletTransaction.objects.filter(
                reference=f"REG-REFUND-{registration.pk}",
                transaction_type=WalletTransaction.TransactionType.REFUND,
                status=WalletTransaction.Status.COMPLETED,
            ).count(),
            1,
        )
        self.assertTrue(registration.refund_processed)
        self.assertEqual(registration.status, Registration.Status.NOT_PLAYING)

        changed_again, _ = mark_not_playing_and_refund(registration.pk)
        self.assertFalse(changed_again)
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, Decimal("50.00"))

    def test_cancelled_tournament_credits_verified_upi_payment_to_wallet_once(self):
        registration = self.make_registration(status=Registration.Status.CONFIRMED)

        refunded, _ = cancel_tournament_and_refund(self.tournament.pk)

        self.assertEqual(refunded, 1)
        registration.refresh_from_db()
        wallet = Wallet.objects.get(user=self.user)
        self.assertEqual(wallet.balance, Decimal("50.00"))
        self.assertEqual(registration.status, Registration.Status.REFUNDED)
        self.assertTrue(registration.refund_processed)
        self.assertEqual(
            WalletTransaction.objects.filter(
                reference=f"TOURNEY-CANCEL-REFUND-{registration.pk}",
                transaction_type=WalletTransaction.TransactionType.REFUND,
                status=WalletTransaction.Status.COMPLETED,
            ).count(),
            1,
        )

        refunded_again, _ = cancel_tournament_and_refund(self.tournament.pk)
        self.assertEqual(refunded_again, 0)
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, Decimal("50.00"))

    def test_final_hour_self_refund_credits_verified_upi_to_inr_wallet(self):
        self.tournament.start_time = timezone.now() + timedelta(minutes=30)
        self.tournament.save(update_fields=["start_time"])
        registration = self.make_registration(status=Registration.Status.CONFIRMED)
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("tournaments:self_refund", args=[registration.pk])
        )

        self.assertEqual(response.status_code, 302)
        registration.refresh_from_db()
        wallet = Wallet.objects.get(user=self.user)
        self.assertEqual(wallet.balance, Decimal("50.00"))
        self.assertEqual(registration.status, Registration.Status.REFUNDED)
        self.assertTrue(registration.refund_processed)
        self.assertEqual(
            WalletTransaction.objects.filter(
                reference=f"SELF-REFUND-{registration.pk}",
                transaction_type=WalletTransaction.TransactionType.REFUND,
                status=WalletTransaction.Status.COMPLETED,
            ).count(),
            1,
        )

    def test_unverified_payment_is_not_credited_as_refund(self):
        registration = self.make_registration(
            payment_verified=False,
            status=Registration.Status.CONFIRMED,
        )

        refunded, _ = cancel_tournament_and_refund(self.tournament.pk)

        self.assertEqual(refunded, 0)
        registration.refresh_from_db()
        self.assertEqual(registration.status, Registration.Status.CANCELLED)
        self.assertFalse(registration.refund_processed)
        self.assertFalse(Wallet.objects.filter(user=self.user).exists())
        self.assertFalse(
            WalletTransaction.objects.filter(
                transaction_type=WalletTransaction.TransactionType.REFUND
            ).exists()
        )
