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

## Deployment health check

The public `/health/` endpoint returns HTTP 200 with `{"status":"ok","database":"ok"}` when Django can connect to its configured database. It returns HTTP 503 with a generic unhealthy response if the database is unavailable, without exposing credentials or internal exception details. After a Render deploy, open `https://freefire-touranament-74nr.onrender.com/health/` to verify the deployed app and database connection.

## Render environment variables

Set secrets in Render Dashboard → your web service → Environment; never commit real keys to GitHub:

- Required: `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS` (include the `onrender.com` hostname), and `DATABASE_URL` when using PostgreSQL.
- Email OTP/password reset: `BREVO_API_KEY` and `DEFAULT_FROM_EMAIL` (the sender must be verified in Brevo). SMTP fallback uses `EMAIL_HOST_USER` and `EMAIL_HOST_PASSWORD`.
- Tournament entry UPI: `FF_ARENA_UPI_ID` and optional `FF_ARENA_UPI_NAME`. The registration page shows an amount-specific QR and an “Open UPI app” link, then asks for the player's Profile UID, Free Fire UID and UTR. Registration remains pending until admin checks the actual incoming UPI/bank statement and verifies it.
- AI evidence proposal: `OPENAI_API_KEY` (optional; without it, use manual admin review).

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

The admin sets room details only for verified registrations. Players can see them only after payment verification and must press YES within 60 seconds. Cancellation/refund actions should be reviewed carefully because real UPI transfers require manual reconciliation. To process expired confirmations, run:

```powershell
python manage.py process_expired_confirmations
```

This command is not a background scheduler. Configure Windows Task Scheduler or a server scheduler to run it regularly. Admin can also cancel a tournament using the tournament admin action; the service records wallet refunds for eligible paid registrations.

## Wallet and payments — important

- Wallet deposits open a UPI payment intent using `FF_ARENA_UPI_ID`. This only opens the player's UPI app; it does not verify payment automatically. The deposit remains pending until an admin reconciles the actual bank/UPI statement, records the bank reference in the Deposit Request admin page, and runs the approval action. Never approve based only on a screenshot or a player's claim.
- Tournament entry fees are paid directly to the receiving UPI account. Players submit the transaction UTR; admin must match the UTR and exact amount against the real receiving account statement before confirming registration. The internal Admin Wallet is only a website ledger, not the actual bank/UPI balance.
- Withdrawals reserve/debit the requested amount and remain pending until the admin has actually transferred the money through UPI and records the payout reference in admin. The website does not send UPI payments by itself.
- BR kill rewards are calculated at ₹5 per admin-approved kill with a 2-kill minimum. Admin reviews the video/screenshots, then manually transfers the approved amount to the player's saved UPI ID or QR outside the website and enters the real UTR in the Kill Submission admin page before marking it paid. Tournament winner prizes use the same manual UPI process: set the Winner UID, inspect the winner's saved UPI/QR, transfer externally, enter the real UTR, then use the admin action to mark it paid. VS mode does not use the BR kill reward rule.
- This UPI intent/manual reconciliation flow is not an automatic payment integration. Do not advertise automatic deposits or payouts or use it for real-money operations until a supported, authorized verification/payout integration, reconciliation, security review and automated tests are in place.

## AI match-history review

The optional adapter in `apps/tournaments/ai_review.py` samples frames from the submitted video using FFmpeg and sends those frames plus two screenshots to the configured OpenAI Responses API. It requires:

- `OPENAI_API_KEY` configured in the local/server environment (never commit it).
- FFmpeg installed on the server and available on `PATH`, or set `FFMPEG_PATH`.
- A model available to your API account, configured with `OPENAI_KILL_REVIEW_MODEL`.

Players must consent to AI processing on the upload form. If AI is unavailable, the evidence is still saved for manual review. AI output is only a proposal; an admin must inspect the evidence and approve/correct the kill count before wallet reward accounting. The upload checks file extensions and size; verify the match video duration and evidence manually.

## UPI deposit setup

Set `FF_ARENA_UPI_ID` in the Render environment to the UPI ID owned by the receiving account. Do not put API keys or bank credentials in source control. The UPI button only opens a UPI app with the amount prefilled; payment confirmation does not return to this website. Admin must match the actual incoming bank/UPI statement, enter the bank reference on the pending Deposit Request, and approve it in Django admin. Withdrawals still require an admin to send the payout manually and record its payout reference. The internal Admin Wallet is accounting inside the website, not a bank account.

## Automatic Cashfree checkout setup

The automatic checkout route is `/accounts/wallet/deposit/automatic/`. It creates a server-side Cashfree order, opens the existing secure checkout template, and credits the wallet only after the server verifies the order and successful payment. The browser redirect by itself never credits a wallet.

For sandbox testing, add these Render Environment variables (do not commit values):
- `CASHFREE_CLIENT_ID` — Cashfree sandbox App ID
- `CASHFREE_CLIENT_SECRET` — Cashfree sandbox secret
- `CASHFREE_MODE=sandbox`

Configure Cashfree's sandbox webhook URL as `https://YOUR-RENDER-HOST/accounts/wallet/deposit/cashfree/webhook/`. Set the return URL to `https://YOUR-RENDER-HOST/accounts/wallet/deposit/cashfree/return/` if the dashboard requests one; the order API also receives both URLs. The webhook signature is verified before processing. Test with sandbox transactions first.

For real money, switch to production credentials and `CASHFREE_MODE=production` only after Cashfree has approved the actual tournament/entry-fee/prize use case and required business/KYC checks. A free account or sandbox keys do not authorize live real-money gaming. The code does not send withdrawals automatically; withdrawals remain admin-reviewed until an approved payout API is separately integrated and tested.

## Phone OTP and DigiLocker setup status

- Email OTP remains the current working registration verification. Phone numbers are stored, but `phone_verified` remains false until a real SMS/phone verification provider is integrated. Do not mark it true manually or treat a typed number as verified. A provider account/configuration is required; do not put private credentials in GitHub.
- DigiLocker API access requires registering the organization in the official Partner Organisation Portal and completing their vetting/approval process. After approval, implement against the credentials and technical docs supplied to that organization. Until then, do not collect DigiLocker credentials or claim official document verification.
- WhatsApp automated delivery likewise requires an approved WhatsApp Business/API provider. Existing links are not automatic messages.

## External services not yet integrated

- Phone-number OTP verification provider.
- Verified automatic UPI deposit and payout provider/webhooks.
- Automatic WhatsApp message delivery via an approved WhatsApp Business API/provider. The existing notification helper only builds click-to-chat links.
- Production-grade private media storage and access controls. Local media serving is enabled only in development.

GitHub Actions is configured to check migration consistency, apply migrations, run `manage.py check`, and run tests on pushes and pull requests. Passing these checks is not a substitute for payment-provider and production security review.
