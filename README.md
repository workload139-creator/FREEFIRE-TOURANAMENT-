# FREEFIRE-TOURANAMENT-
# FF Tournament Website

A modular Django-based Free Fire tournament management platform.

## Planned features

- Player registration and account security
- Free Fire UID linking
- Tournament management
- Player and admin wallet accounting
- Verified deposits and payouts
- Tournament refunds
- Kill verification and rewards
- Leaderboards
- WhatsApp notifications
- Administrative audit logs

## Development setup

1. Install Python 3.11 or later.
2. Create and activate a virtual environment.
3. Install dependencies:

   `pip install -r requirements.txt`

4. Copy `.env.example` to `.env`.
5. Set a unique local `DJANGO_SECRET_KEY`.
6. Run migrations:

   `python manage.py migrate`

7. Start the development server:

   `python manage.py runserver`

## Security

Never commit `.env`, passwords, payment secrets, or production credentials.

Do not enable real payments until the payment verification, ledger,
refund, payout and automated test flows have been implemented and reviewed.
