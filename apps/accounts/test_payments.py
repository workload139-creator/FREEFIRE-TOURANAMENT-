from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import DepositRequest, Wallet


class ManualUPIDepositTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="upi_player",
            email="upi@example.com",
            phone_number="9876543210",
            password="A-Strong-Testing-Password-123!",
        )
        self.wallet = Wallet.objects.create(user=self.user)
        self.client.force_login(self.user)

    @patch.dict("os.environ", {"FF_ARENA_UPI_ID": "arena@example"})
    def test_deposit_creates_pending_request_without_crediting_wallet(self):
        response = self.client.post(
            reverse("accounts:deposit"),
            {"amount": "10.00"},
        )
        self.assertEqual(response.status_code, 200)
        deposit = DepositRequest.objects.get(wallet=self.wallet)
        self.assertEqual(deposit.amount, Decimal("10.00"))
        self.assertEqual(deposit.status, DepositRequest.Status.PENDING)
        self.assertContains(response, "UPI QR")
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("0.00"))

    @patch.dict("os.environ", {"FF_ARENA_UPI_ID": "arena@example"})
    def test_submitted_utr_does_not_credit_until_admin_approval(self):
        deposit = DepositRequest.objects.create(wallet=self.wallet, amount=Decimal("10.00"))
        response = self.client.post(
            reverse("accounts:deposit"),
            {
                "confirm_payment": "1",
                "deposit_id": str(deposit.pk),
                "utr": "123456789012",
            },
        )
        self.assertEqual(response.status_code, 200)
        deposit.refresh_from_db()
        self.assertEqual(deposit.payment_reference, "123456789012")
        self.assertEqual(deposit.status, DepositRequest.Status.PENDING)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("0.00"))
