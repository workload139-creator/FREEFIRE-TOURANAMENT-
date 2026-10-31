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

The existing evidence-review flow uses four local reviewers and does not call any external AI service:

- Assessment 1 reads the two uploaded Free Fire history screenshots with local OCR.
- Assessment 2 samples frames from the submitted match-history video and reads visible text with local OCR.
- Agent 1 compares readable UID, kill count, date and BR/VS mode fields across the screenshots and video.
- Agent 2 checks evidence fingerprints, duplicate/integrity signals and missing evidence.

Tesseract OCR and FFmpeg (or the bundled `imageio-ffmpeg` binary) must be available on the host. These local OCR/rule-based checks are advisory: they cannot query Garena or guarantee the source media is genuine. Unreadable fields, missing match identifiers, mismatches or uncertainty stay in Admin Review. This uploaded-evidence flow does not independently authorize automatic rewards. Keep the separate Live AI pipeline gated until real device streaming, frame assessment, event deduplication and exact-once reward tests pass.

## Durable media and Android app data

Set `CLOUDINARY_URL` in Render Environment to enable Cloudinary-backed storage for profile photos, UPI QR images, match-history screenshots and videos. The repository config keeps local storage for development when the variable is blank. After enabling Cloudinary, players should re-upload any old profile photo that was previously stored only on Render's temporary disk. Pending match evidence is retained until review; reviewed evidence is retained for a 90-day audit window.

The Android app keeps WebView DOM storage and cookies enabled and flushes session cookies when the app pauses. Normal APK updates with the same package and signing key preserve app data. The website database remains the source of truth, so player accounts, wallets and tournament records are not dependent on the phone cache. Uninstalling the app, clearing its storage or losing/resetting the phone can still remove local app data; no app can guarantee otherwise.

## UPI deposit setup

Set `FF_ARENA_UPI_ID` in the Render environment to the UPI ID owned by the receiving account. Do not put API keys or bank credentials in source control. The UPI button only opens a UPI app with the amount prefilled; payment confirmation does not return to this website. Admin must match the actual incoming bank/UPI statement, enter the bank reference on the pending Deposit Request, and approve it in Django admin. Withdrawals still require an admin to send the payout manually and record its payout reference. The internal Admin Wallet is accounting inside the website, not a bank account.


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
