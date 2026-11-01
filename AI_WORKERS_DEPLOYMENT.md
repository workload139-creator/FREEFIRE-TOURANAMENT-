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
