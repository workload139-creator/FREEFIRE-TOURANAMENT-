# FF Arena — Free Fire Tournament Website

Modular Django website for player accounts, tournament registrations, wallet ledgers, room confirmation, match-history evidence, leaderboards and admin review.

## Structure

- `config/`: Django settings and URL routing.
- `apps/accounts/`: player accounts, wallet, deposits, withdrawal requests and accounting models.
- `apps/tournaments/`: tournaments, registrations, room confirmation, refunds, evidence uploads, AI proposal adapter and leaderboards.
- `apps/tournaments/management/commands/`: maintenance commands.
- `templates/`: Django templates.
- `static/`: CSS and JavaScript.
- `main.py`: shared project-level constants and feature flags.
- `.github/workflows/django-checks.yml`: automatic migration, system-check and test workflow.

## Local setup (Windows / PowerShell)

1. Install Python 3.12 (or a supported Python version).
2. Open this repository folder in VS Code.
3. Create a virtual environment:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

4. Install dependencies:

   ```powershell
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

5. Copy `.env.example` to `.env`. Keep real API keys only in the ignored local `.env` file. Never commit secrets.
6. Apply the committed migrations and run checks:

   ```powershell
   python manage.py migrate
   python manage.py check
   python manage.py test
   ```

7. Create an admin account and start the site:

   ```powershell
   python manage.py createsuperuser
   python manage.py runserver
   ```

Open `http://127.0.0.1:8000/`; the admin site is at `http://127.0.0.1:8000/admin/`.

## Room confirmation and refunds

The admin sets room details for eligible registrations. Players can see them only after payment verification and must press YES within 60 seconds. To process expired confirmations, run:

```powershell
python manage.py process_expired_confirmations
```

This command is not a background scheduler. Configure Windows Task Scheduler or a server scheduler to run it regularly. Admin can also cancel a tournament using the tournament admin action; the service records wallet refunds for eligible paid registrations.

## Wallet and payments — important

- Wallet deposits open a UPI payment intent using `FF_ARENA_UPI_ID`. This only opens the player's UPI app; it does not verify payment automatically. The deposit remains pending until an admin reconciles the actual bank/UPI statement, records the bank reference in the Deposit Request admin page, and runs the approval action. Never approve based only on a screenshot or a player's claim.
- Tournament entry fees are debited from the player wallet. Admin payment review checks the corresponding wallet ledger before confirming a registration.
- Withdrawals reserve/debit the requested amount and remain pending until the admin has actually transferred the money through UPI and records the payout reference in admin. The website does not send UPI payments by itself.
- Kill rewards are credited to the player wallet only after an admin enters the approved kill count and the admin wallet has sufficient balance. This is internal/demo wallet accounting, not a bank transfer.
- This UPI intent/manual reconciliation flow is not an automatic payment integration. Do not advertise automatic deposits or payouts or use it for real-money operations until a supported, authorized verification/payout integration, reconciliation, security review and automated tests are in place.

## AI match-history review

The optional adapter in `apps/tournaments/ai_review.py` samples frames from the submitted video using FFmpeg and sends those frames plus two screenshots to the configured OpenAI Responses API. It requires:

- `OPENAI_API_KEY` configured in the local/server environment (never commit it).
- FFmpeg installed on the server and available on `PATH`, or set `FFMPEG_PATH`.
- A model available to your API account, configured with `OPENAI_KILL_REVIEW_MODEL`.

Players must consent to AI processing on the upload form. If AI is unavailable, the evidence is still saved for manual review. AI output is only a proposal; an admin must inspect the evidence and approve/correct the kill count before wallet reward accounting. The upload checks file extensions and size; verify the match video duration and evidence manually.

## UPI deposit setup

Set `FF_ARENA_UPI_ID` in the Render environment to the UPI ID owned by the receiving account. Do not put API keys or bank credentials in source control. The UPI button only opens a UPI app with the amount prefilled; payment confirmation does not return to this website. Admin must match the actual incoming bank/UPI statement, enter the bank reference on the pending Deposit Request, and approve it in Django admin. Withdrawals still require an admin to send the payout manually and record its payout reference. The internal Admin Wallet is accounting inside the website, not a bank account.

## External services not yet integrated

- Phone-number OTP verification provider.
- Verified automatic UPI deposit and payout provider/webhooks.
- Automatic WhatsApp message delivery via an approved WhatsApp Business API/provider. The existing notification helper only builds click-to-chat links.
- Production-grade private media storage and access controls. Local media serving is enabled only in development.

GitHub Actions is configured to check migration consistency, apply migrations, run `manage.py check`, and run tests on pushes and pull requests. Passing these checks is not a substitute for payment-provider and production security review.
