# ADR-0026: Native Android app

- Status: Accepted
- Date: 2026-10-19

## Context
Most of our users (Kenyan insurance agents) work from Android phones, often mid-range ones on patchy mobile
data. The product owner chose a **native Kotlin + Jetpack Compose app, Android only**, that can be "updated
over the air". The web app stays the full product; the app covers what agents do on the move.

## Decision
- **Stack:**
  - Kotlin, Jetpack Compose and Material 3, in `apps/android` (Gradle 9, AGP 9, a version catalog);
  - Ktor client with kotlinx.serialization;
  - DataStore for settings;
  - manual dependency injection (an `AppContainer`): no DI framework until the app needs one.
- **minSdk 26 (Android 8)** covers almost every phone in use; compileSdk and targetSdk are the latest (37).
- **Sign-in uses the existing auth service; nothing new on the server:**
  1. `POST /api/auth/sign-in/email` through the web app's `/api/auth` proxy. The app sends its site URL as
     `Origin` (Better Auth's CSRF check, as the Expo integration does) and receives a session token in
     `set-auth-token` (Better Auth `bearer` plugin).
  2. With two-factor on, the response says `twoFactorRedirect`. The app keeps that response's cookies **in
     memory only** and sends the code to `/api/auth/two-factor/verify-totp`, which returns the session token.
  3. The agency is chosen with `/api/auth/organization/list` and `/set-active`.
  4. `GET /api/auth/token` (bearer) mints the 15-minute API token, which carries the agency and role. The
     app refreshes it shortly before it expires and after a 401.
  5. The session token is the only long-lived secret. It is encrypted with an Android Keystore key
     (AES-GCM, never exported) before it is stored. Sign-out revokes it on the server.
- **API access:** Caddy now routes `/api/v1/*` on `api.<DOMAIN>`. Every route there already requires the
  short-lived token; `/internal`, `/docs` and `/metrics` stay closed.
- **"Over the air" updates, within Google Play's rules:** Play forbids apps from downloading executable
  code, so there is no code push. Instead:
  1. **Play in-app updates.** If the installed version is below `min_version_code` from
     `GET /api/v1/public/app-config`, the app blocks with an *immediate* update. If a newer version exists,
     it offers a *flexible* update that downloads in the background and asks to restart.
  2. **Remote config** from the same endpoint: `notice` (a message to everyone) and `features` (switches),
     set by environment on the server, with no app release.
  3. **Staged rollouts** on Play for every release.
  4. **Server-driven data:** screens show what the API returns, so most product changes need no release.
- **Release:**
  - Play App Signing, with an upload key kept outside the repo (CI secrets).
  - `versionCode` comes from the CI run number.
  - The application ID is a Gradle property. It **must be final before the first Play upload** (it can
    never change afterwards) and waits on the product name (D7).
- **Scope of the first slice (A1):**
  - sign-in (with two-factor) and agency choice;
  - home with today's numbers;
  - clients: search, details, call and WhatsApp;
  - account: switch agency, sign out, check for updates.
  - Later: renewals, quotes, payments (M-Pesa prompt), offline notes and photos, push notifications (FCM,
    which needs a device-token table and send jobs).

## Consequences
- No new auth code or secrets on the server; the app uses the same flows as the web.
- One Kotlin codebase for Android only. An iPhone app would be separate (Kotlin Multiplatform remains
  possible later, because the data layer has no Android types in it).
- CI builds, lints and unit-tests the app on every PR; Play uploads are a manual, documented step until the
  Play Console account exists.
