# FF Arena Native Android Migration

## Product contract

- Android must render its own native screens. No WebView, Custom Tabs, or website-page fallback for app features.
- The website remains an independent Django-rendered UI on Render.
- Both clients use the same Django backend, PostgreSQL records, account identities, tournament rules, wallet ledger, and Cloudinary media.
- Android is distributed as a directly installable, release-signed APK. Google Play publication is not part of this project.
- GitHub Actions builds the Android APK for every main-branch code push, including backend/API changes, and publishes a versioned release. Android still requires the user's confirmation to install an APK update.
- Live gameplay sharing remains an explicit, user-consented Android MediaProjection + LiveKit feature. Viewer tokens remain server-issued and restricted to eligible tournament participants.

## Current repository audit (2026-11-02)

The current Android client is a hybrid: `MainActivity.java` creates a native-looking shell but opens Django website routes in a WebView for most feature actions. It is not yet a full native client.

Existing Android-specific server APIs are limited:
- `GET /tournaments/api/`: public tournament list.
- `GET /accounts/api/me/`: authenticated profile read.
- `GET /accounts/api/wallet/`: authenticated wallet/history read.
- LiveKit publisher integration exists in `TournamentLiveShareController.kt`; the leaderboard viewer currently runs in the website template.

A complete native client cannot safely be delivered by merely hiding the WebView. Native endpoints and screens are still required for login/session persistence, registration/payment state, ready-check/room access, leaderboard/watch, profile editing/photo upload, social feed/followers/chat, party rooms, wallet requests, history, and settings. Sensitive money/reward operations must remain server-authoritative and idempotent.

## Delivery phases

1. **Native foundation** — Compose UI, navigation, theme, API client, secure session handling, loading/error/retry states, version/update handling. Remove all website WebView navigation from the production app only after parity is verified.
2. **Account and tournament core** — native login/register/OTP flows, profile, tournament discovery/details, registration, My Tournaments, ready-check and room access.
3. **Live tournament experience** — native leaderboard, server-authorized LiveKit viewer, consent-based screen publishing, LiveKit lifecycle/stop handling, and reconnect behavior.
4. **Wallet and community** — native wallet/ledger, admin-verified payment requests, withdrawals, posts/images, followers/following, direct chat and voice party rooms.
5. **Release hardening** — API contract tests, Android unit/UI tests, signed APK build, update-signature/version tests, and two-device real-network verification.

## Safety and compatibility rules

- Do not change or duplicate existing tournament/wallet business rules in Android. The server remains the source of truth.
- Never embed LiveKit API secrets, Django secret keys, payment secrets, or signing keys in the APK.
- Keep existing user accounts and database rows; do not migrate to a second database.
- Do not remove Django website routes or alter the website UI as part of the Android migration.
- Do not publish a partial native app as a replacement for the working app. Switch the launcher to the native shell only when the relevant feature set is implemented and tested.
- Do not claim real-device verification until at least two Android devices have tested publishing and viewing over a real network.
