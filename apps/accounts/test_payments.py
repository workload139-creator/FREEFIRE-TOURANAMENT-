from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.cashfree import CashfreeError
from apps.accounts.models import DepositRequest, Wallet


class CashfreeWalletCheckoutTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="cashfree_player",
            email="cashfree@example.com",
            phone_number="9876543210",
            password="A-Strong-Testing-Password-123!",
        )
        self.wallet = Wallet.objects.create(user=self.user)
        self.client.force_login(self.user)

    @patch("apps.accounts.cashfree._config", side_effect=CashfreeError("missing keys"))
    def test_missing_keys_never_creates_or_credits_deposit(self, _config):
        response = self.client.post(
            reverse("accounts:cashfree_deposit"),
            {"amount": "10.00"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Automatic payment abhi setup nahi hai")
        self.assertEqual(DepositRequest.objects.count(), 0)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("0.00"))

    @patch("apps.accounts.view.create_order", return_value={"payment_session_id": "test-session"})
    @patch("apps.accounts.view._config", return_value=("sandbox-id", "sandbox-secret", "sandbox", "https://sandbox.cashfree.com/pg"))
    def test_creates_pending_order_and_never_credits_before_payment(self, _config, create_order):
        response = self.client.post(
            reverse("accounts:cashfree_deposit"),
            {"amount": "10.00"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/cashfree_checkout.html")
        deposit = DepositRequest.objects.get(wallet=self.wallet)
        self.assertEqual(deposit.amount, Decimal("10.00"))
        self.assertEqual(deposit.status, DepositRequest.Status.PENDING)
        self.assertTrue(deposit.payment_reference.startswith(f"ffw_{self.user.pk}_"))
        create_order.assert_called_once()
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("0.00"))
