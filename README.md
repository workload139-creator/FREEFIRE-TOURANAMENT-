# FF Tournament Website

A modular Django-based Free Fire tournament management platform.

## Project structure

- `apps/accounts/`: player accounts, wallet, deposits and admin ledger.
- `apps/tournaments/`: tournament models, registration, room confirmation, refunds and kill-reward calculation.
- `apps/tournaments/management/commands/`: scheduled maintenance commands.
- `templates/`: Django templates.
- `static/`: CSS and JavaScript.
- `config/settings/`: shared, development and production settings.

## Development setup

1. Install Python 3.11 or later.
2. Create and activate a virtual environment.
3. Install dependencies: `pip install -r requirements.txt`.
4. Copy `.env.example` to `.env` and set a unique local `DJANGO_SECRET_KEY`.
5. Generate and apply migrations:
   ```powershell
   python manage.py makemigrations accounts tournaments
   python manage.py migrate
   ```
6. Check configuration and run tests:
   ```powershell
   python manage.py check
   python manage.py test
   ```
7. Start the development server: `python manage.py runserver`.

## Expired room confirmations

A player who receives room details must press YES within 60 seconds. To process expired confirmations and record eligible wallet refunds, run:

```powershell
python manage.py process_expired_confirmations
```

This command must be scheduled to run regularly using Windows Task Scheduler or a server scheduler. It does not run automatically just because the website is open.

## Important implementation limits

- Tournament entry fees are debited from the player wallet and remain pending until an admin uses the payment-verification action. Only mark them verified after checking the matching ledger.
- Deposits stay pending until an admin checks the real payment receipt/reference and uses the approval action. No payment provider is connected yet; a typed UPI reference alone is not proof of payment.
- WhatsApp links are click-to-chat links; automatic delivery needs an approved WhatsApp API/provider.
- Kill reward calculations are helper logic only. AI evidence analysis, evidence upload persistence and final payout orchestration still require implementation and tests.
- Phone/UID verification flags exist, but a live OTP provider and automated verification flow are not connected.
- Do not enable real-money payouts until provider verification, refund/payout ledger logic, security review and automated tests are complete.

Never commit `.env`, passwords, payment secrets, or production credentials.
