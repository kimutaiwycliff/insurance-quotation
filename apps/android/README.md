# Android app

Native Kotlin and Jetpack Compose (ADR-0026). It covers what agents do away from a desk; the web app remains
the full product.

## What it does (first slice)
- **Sign in:** email and password, with two-factor codes; choose an agency if you belong to several.
- **Home:** today's numbers (tasks, renewals due, clients, policies, premiums to pass on, premium written).
- **Clients:** search by name or phone, client details, **Call**, **WhatsApp** (with a greeting), email,
  and a link to the full page on the web.
- **Account:** switch agency, check for updates, sign out.
- **Updates and remote config:** from `GET /api/v1/public/app-config`.
  - Versions below `ANDROID_MIN_VERSION_CODE` must update through Google Play before use.
  - Newer versions are offered as a background download.
  - `APP_NOTICE` shows a message to everyone; `APP_FEATURES` turns remote switches on.

## Run it against your local stack
1. `make up` in the repository root. Create an account and agency on http://localhost:3000.
2. Start an Android emulator (Android Studio → Device Manager).
3. In `apps/android`, run `./gradlew installDebug`, or open the folder in Android Studio and press Run.
   - Debug builds talk to `http://10.0.2.2:3000` (site and sign-in) and `:8000` (API): the emulator's
     address for your computer.
   - On a real phone on the same Wi-Fi, use your computer's IP:
     `./gradlew installDebug -PsiteUrl=http://192.168.1.20:3000 -PapiUrl=http://192.168.1.20:8000`.
     Also add that IP to `src/debug/res/xml/network_security_config.xml`.
4. Sign in with the account from step 1.

Requirements: JDK 17 or newer (`JAVA_HOME`) and the Android SDK (`ANDROID_HOME`, or `local.properties` with
`sdk.dir`). The Gradle wrapper downloads Gradle itself, checksum-pinned.

## Checks
`make android-check` (lint, unit tests, debug build). CI also builds a minified release on every PR.

## Layout
```
app/src/main/java/app/brokeros/android/
  core/     endpoints, JWT expiry, phone links, Keystore-encrypted session storage
  data/     auth (Better Auth via the web proxy), session state machine, API client, models
  update/   app config (remote switches) and Google Play in-app updates
  ui/       theme, sign-in screens, home, clients, account
app/src/test/  unit tests (Ktor mock engine: no server needed)
```

## Releasing
See `docs/runbooks/android-release.md`.
