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

## Amendment (2026-10-19): distribution without Google Play, for now
The product owner has no Play Console account yet, so the app is downloaded from our own site until there is.

- **Two flavors of the same app:**
  - **direct:** downloaded from `https://app.<DOMAIN>/download`; updates itself.
  - **play:** for the Play Store later; Play in-app updates.

  The only differences are the updater and the `REQUEST_INSTALL_PACKAGES` permission, which the play build
  does not have.
- **Self-update (direct):**
  - `GET /api/v1/public/app-config` now also returns `apk_url` and `apk_sha256` (`ANDROID_APK_URL`,
    `ANDROID_APK_SHA256`).
  - The app streams the APK and hashes it; it refuses to install unless the SHA-256 matches. With nothing
    published, it does not install.
  - It hands the file to Android's package installer; the person allows installs from the app once.
  - Android itself refuses an update not signed with the installed app's key.
  - `ANDROID_MIN_VERSION_CODE` still forces updates.
- **Signing:**
  - One release key, made once with `apps/android/scripts/new-signing-key.sh` and kept out of the repo, in a
    password manager plus a second safe place. Losing it means every user must uninstall and reinstall.
  - For Play later, enrol this same key in Play App Signing, so direct installs can move to Play updates.
- **Hosting:** Caddy serves `deploy/downloads/` on the VM at `/downloads/`, with APK content type and attachment
  disposition. `apps/android/scripts/release-apk.sh` builds, hashes and prints the publish steps.
- **The download page** (`/download`, public) shows the button, install steps and the fingerprint. The sign-in
  page links to it.

## Amendment (2026-10-19): offline use and background notifications
- **Reads work offline:**
  - Every successful GET is saved in app-private storage (`filesDir/api-cache`, at most 400 answers,
    oldest dropped first).
  - With no connection, the saved answer is shown with an "offline, saved … ago" banner.
  - Saved answers carry no ETag, so offline copies can be viewed, not edited.
- **Some writes queue offline:** logging an activity, adding or editing or completing a task, and adding a lead.
  - They go to an outbox (`filesDir/outbox.json`) with their `Idempotency-Key` or `If-Match`, and are sent in
    order when the connection returns (network callback, app resume, and the background worker).
  - A change the server refuses later (for example the record changed meanwhile) is shown, never dropped
    silently.
  - Money, issuing and anything final stay online-only.
- **Client data on the phone:** the cache and outbox hold client data. They are app-private, excluded from
  backups and device transfer (data extraction rules), and **wiped on sign-out**, together with the
  background job and any notifications shown.
- **Background notifications without Google services:**
  - WorkManager runs every 30 minutes on any network: it sends queued changes and turns new unread in-app
    notifications into phone notifications. Tapping one opens the notification list.
  - Android 13+ asks permission once.
  - Push through FCM can replace the polling later; it needs a Firebase project, plus a device-token table and
    send jobs on the server.
- **Two-factor setup and M-Pesa connection** are now in the app: Better Auth's `two-factor/enable`,
  `verify-totp` and `disable` with the bearer session, and the API's `/mpesa/connection`.

