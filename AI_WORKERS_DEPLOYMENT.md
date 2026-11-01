# FF Arena AI worker deployment

## What this Blueprint adds

- `ff-arena-live-ai-worker`: Docker worker with Tesseract OCR installed. It subscribes to eligible LiveKit player streams and submits OCR candidates to the website.
- `ff-arena-payment-ai-worker`: separate Docker worker that creates advisory eligibility/reward assessments for candidate events.

The workers share the existing website's Django secret and database connection through Render `fromService` references. LiveKit credentials and the ingest token are referenced from the existing website service; no secret is stored in this repository.

## Before syncing the Blueprint

In the existing Render web service named `FREEFIRE-TOURANAMENT-`, confirm these environment keys exist and are valid:

- `DJANGO_SECRET_KEY`
- `DATABASE_URL`
- `LIVEKIT_URL`
- `LIVEKIT_API_KEY`
- `LIVEKIT_API_SECRET`
- `LIVE_AI_INGEST_TOKEN`

The web service must also have the matching `LIVE_AI_INGEST_TOKEN` value configured for its private candidate-ingest endpoint. Do not commit or paste any secret into GitHub.

The Blueprint provisions two `starter` background workers in Singapore. These are paid Render resources. Review the current Render pricing and approve the cost in the Render Dashboard before syncing the Blueprint. Do not change the existing website service's type, runtime, or start command as part of this worker rollout.

## Current safety boundary

These workers do not automatically approve kills or credit wallets. Live OCR is a candidate signal, not proof of the killer. Payment AI writes an assessment/proposal only. Admin verification and the existing idempotent settlement path remain the payout gate until reliable killer attribution, match/time evidence, restart/concurrency idempotency, and end-to-end payout tests pass.

The two workers are not 50 independent physical compute instances. The database has per-player logical Live/Payment slots; actual concurrent stream capacity must be load-tested before advertising a 50-player guarantee.

## Post-deploy verification

1. Confirm both workers build successfully and remain running.
2. Check Live worker logs for LiveKit connection, stream subscription, UID verification, and candidate submission.
3. Check Payment worker logs for candidate assessment cycles and slot heartbeats.
4. Create a controlled test tournament/session and use test evidence only.
5. Confirm duplicate candidate submissions create one event and never produce duplicate wallet transactions.
6. Keep production auto-credit disabled until all attribution and accounting tests pass.
