# FF Arena: self-hosted AI plan (no paid AI APIs)

FF Arena's four verification roles are implemented as project-owned Python logic and open-source computer-vision components. The app must not call OpenAI, Ollama Cloud, or paid inference APIs.

## Four project-owned roles

1. **Assessment 1 — player identity:** validate the registered Free Fire UID against profile/history evidence and account registration.
2. **Assessment 2 — match evidence:** inspect history screenshots, timestamps, match context, and killfeed evidence.
3. **Agent 1 — live evidence collector:** consume the player's LiveKit stream, sample frames, run local OCR/vision checks, and submit candidate evidence.
4. **Agent 2 — reward safety:** re-check registration/payment/session eligibility, distinct event fingerprints, minimum verified kills, and idempotent ledger settlement.

These roles are not four independent large language models. They are independently testable, explainable local agents. Open-source OCR/vision models may be run locally or on a machine the project owner controls. A model is not considered trained merely because sample screenshots were uploaded; training requires labelled examples, train/validation splits, evaluation, and versioned model artifacts.

## No-paid-compute deployment policy

- Do not provision Render Starter background workers automatically.
- Keep the existing website service unchanged.
- During development, run the local AI worker commands on the owner's computer.
- A free website host is not a reliable always-on GPU/CPU worker. For 24/7 processing, use an owner-controlled computer/server or explicitly choose a hosting budget later.
- Do not store model weights, private evidence, or credentials in GitHub.

## Safety and payout boundary

OCR or a visual model can identify a possible killfeed event, but cannot by itself prove which registered player made the kill. The system must hold ambiguous events for Admin review. No AI worker may directly credit a wallet. Only the transaction-safe, idempotent Admin-approved settlement path can issue a reward, and duplicate events must never create a second credit.

## Validation required before production

- UID/profile consistency and evidence date-window tests.
- BR/VS mode and tournament/session/payment eligibility tests.
- Duplicate fingerprints, repeated worker delivery, concurrent approval, and worker restart tests.
- Correct second-distinct-verified-kill reward threshold and tournament-specific currency tests.
- Evidence privacy and permanent storage tests.
- LiveKit disconnect/reconnect, frame sampling, and realistic concurrency tests.
- Full browser tests for player pages and Admin actions.

## Windows local start

1. Install Python dependencies with `pip install -r requirements.txt`.
2. Install the free Tesseract OCR engine and make sure `tesseract.exe` is in PATH.
3. Create a local `.env` (never commit it) with `DJANGO_SECRET_KEY`, a reachable `DATABASE_URL`, `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, and `LIVE_AI_INGEST_URL` plus a matching private `LIVE_AI_INGEST_TOKEN`.
4. Run PowerShell as the project folder and execute `powershell -ExecutionPolicy Bypass -File .\scripts\run_ff_arena_local_ai.ps1`.
5. Keep both worker windows open while testing. Closing them stops local processing.

The launcher checks Django and the two commands, then starts Live AI and Payment AI in separate PowerShell windows. It does not install software or expose secrets. The website's private ingest endpoint must have the same `LIVE_AI_INGEST_TOKEN` configured.

## Seven-stage product completion checklist

1. Player account/profile/UID and durable media: account model supports Free Fire UID and UID verification; public profile media uses Cloudinary when configured. Verify Cloudinary URL, public photo upload/render, private evidence delivery and Android file chooser before production.
2. BR/VS/Free registration and payment: tournament modes, registration state and manual payment verification exist. Verify entry fees, free tournament cooldown, 49-player capacity, and no double debit/refund.
3. LiveKit room and ready confirmation: LiveKit session/token and room confirmation code exist. Verify real participant camera/video subscription, YES/NO timeout, room credential privacy, disconnect/reconnect.
4. Kill evidence and four local roles: existing evidence review, OCR, video frame extraction and four local rule-based stages exist. Current live OCR is candidate detection only; killer attribution/match/time extraction and labelled model training remain incomplete.
5. Admin review and wallet: admin review and transaction-safe settlement exist. Run duplicate fingerprint, duplicate approval, concurrent approval, second verified kill, and BR/VS reward tests before any auto payout.
6. Social/community and Android: follow/profile/posts/chat/voice and Android wrapper/build workflow exist. Verify mobile photo picker, login cookies, update version/signature, voice permissions, and all routes on a physical Android device.
7. Release gate: run Django tests, `makemigrations --check --dry-run`, `migrate --check`, Render health check, browser player/admin smoke tests, and Android signed build. Do not mark the app production-ready while any critical test fails.

This checklist is deliberately honest: a code path being present is not the same as a successful live end-to-end test.
