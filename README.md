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
- Permanent player photos, UPI QR images and match evidence: set `CLOUDINARY_URL` from your Cloudinary Console. Without it, Render local media is temporary; new uploads will not be durable.
- Email OTP/password reset: `BREVO_API_KEY` and `DEFAULT_FROM_EMAIL` (the sender must be verified in Brevo). SMTP fallback uses `EMAIL_HOST_USER` and `EMAIL_HOST_PASSWORD`.
- Tournament entry UPI: `FF_ARENA_UPI_ID` and optional `FF_ARENA_UPI_NAME`. The registration page shows an amount-specific QR and an “Open UPI app” link, then asks for the player's Profile UID, Free Fire UID and UTR. Registration remains pending until admin checks the actual incoming UPI/bank statement and verifies it.
- AI evidence proposal: default provider uses `OPENAI_API_KEY` and `OPENAI_KILL_REVIEW_MODEL`. To use an OpenAI-compatible vision endpoint instead, set `KILL_REVIEW_PROVIDER=compatible`, `KILL_REVIEW_BASE_URL`, `KILL_REVIEW_API_KEY`, and `OPENAI_KILL_REVIEW_MODEL`. Keep all keys in Render Environment, never in GitHub. A Render service cannot reach your PC's `localhost`; a PC-hosted model needs a secure, reachable endpoint or tunnel.

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

The admin sets room details only for verified registrations. Players can see them only after payment verification and must press YES within 5 minutes. Cancellation/refund actions should be reviewed carefully because real UPI transfers require manual reconciliation. To process expired confirmations, run:

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

The kill-review flow runs two independent multimodal vision checks in dual mode: OpenAI assessment (`OPENAI_API_KEY`, `OPENAI_KILL_REVIEW_MODEL`) and an AI Agent through the configured OpenAI-compatible vision endpoint (`KILL_REVIEW_BASE_URL`, `KILL_REVIEW_API_KEY`, `OLLAMA_KILL_REVIEW_MODEL`). Both receive the two uploaded Free Fire history screenshots and five sampled frames from the submitted 15–30 second video. The prompt checks visible player UID, personal (not team) kills, BR/Clash Squad mode, match date/ID/result where shown, and whether the screenshots and video appear to show the same match.

The app does not have an official Garena match-history API connection. AI must not claim it queried Garena or verified a match online; it can only assess the evidence uploaded by the player. A reward is automatically credited only when both models independently return the same kill count, high confidence, exact registered UID, complete evidence and consistent history, and the website's own payment/registration/UID checks also pass. If either model fails, a field is unreadable, the evidence is incomplete, or the models disagree, the submission remains pending for Admin Review and no automatic reward is issued. The AI Agent is still attempted even if the first AI fails.

FFmpeg samples the video; install it or use the bundled `imageio-ffmpeg` binary. Players must consent to AI processing. Keep all AI keys in Render Environment, never in GitHub.

## Durable media and Android app data

Set `CLOUDINARY_URL` in Render Environment to enable Cloudinary-backed storage for profile photos, UPI QR images, match-history screenshots and videos. The repository config keeps local storage for development when the variable is blank. After enabling Cloudinary, players should re-upload any old profile photo that was previously stored only on Render's temporary disk. Pending match evidence is retained until review; reviewed evidence is retained for a 90-day audit window.

The Android app keeps WebView DOM storage and cookies enabled and flushes session cookies when the app pauses. Normal APK updates with the same package and signing key preserve app data. The website database remains the source of truth, so player accounts, wallets and tournament records are not dependent on the phone cache. Uninstalling the app, clearing its storage or losing/resetting the phone can still remove local app data; no app can guarantee otherwise.

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
- Cloudinary media storage requires the owner's `CLOUDINARY_URL` to be added to Render Environment and a first successful upload test.

GitHub Actions is configured to check migration consistency, apply migrations, run `manage.py check`, and run tests on pushes and pull requests. Passing these checks is not a substitute for payment-provider and production security review.
