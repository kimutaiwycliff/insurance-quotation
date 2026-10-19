# Runbook: releasing the Android app

Until there is a Google Play Console account, the app is downloaded from our own site
(`https://app.<DOMAIN>/download`) and updates itself (ADR-0026 amendment). The Play section at the end is for
later.

## One-time setup
1. **Choose the application ID** with the product name (D7), e.g. `ke.co.<name>.app`. It can never change
   once people have the app installed (a new ID is a different app).
   - Until then builds use the placeholder `app.brokeros.android`.
   - Pass the final one as `APP_ID=… scripts/release-apk.sh …`.
2. **Create the signing key, once, on your computer:**
   ```bash
   apps/android/scripts/new-signing-key.sh        # makes ~/brokeros-signing/release.jks
   ```
   Save the `.jks` file and both passwords in your password manager **and** a second safe place. Phones only
   accept updates signed with this key: lose it and everyone must uninstall and reinstall.
3. Your computer needs JDK 17+ and the Android SDK (see `apps/android/README.md`).

## Each release
1. **Build and sign.** `versionCode` must be higher than the last release:
   ```bash
   export ANDROID_UPLOAD_KEYSTORE=~/brokeros-signing/release.jks ANDROID_UPLOAD_KEY_ALIAS=release \
          ANDROID_UPLOAD_KEYSTORE_PASSWORD=… ANDROID_UPLOAD_KEY_PASSWORD=…
   apps/android/scripts/release-apk.sh <domain> <versionCode> <versionName>
   #   e.g. … release-apk.sh 129-146-10-20.sslip.io 3 0.3.0
   ```
   It builds `apps/android/dist/brokeros-<versionName>.apk`, prints its SHA-256, and prints the next commands.
2. **Upload to the VM:**
   ```bash
   scp apps/android/dist/brokeros-0.3.0.apk ubuntu@<vm-ip>:/opt/brokeros/deploy/downloads/
   ```
   Keep older APKs there for a while, so a bad release can be rolled back.
3. **Publish:**
   - In `/opt/brokeros/.env` on the VM, set `ANDROID_APK_URL=/downloads/brokeros-0.3.0.apk`,
     `ANDROID_APK_SHA256=<printed>` and `ANDROID_LATEST_VERSION_CODE=3`.
   - Then run `deploy/bin/deploy.sh` (or `docker compose -f compose.yaml -f compose.prod.yaml up -d api`).
   - The download page now offers the new APK, and installed apps show "A new version is available".
4. **Check:** on a phone, More → Check for updates downloads, verifies and installs it.

**Forcing an update** (security fix or breaking API change): also raise `ANDROID_MIN_VERSION_CODE`. Older
apps then show "Update to continue" until updated.

**Rolling back:** point `ANDROID_APK_URL` and `ANDROID_APK_SHA256` at the previous APK. Phones that already
installed the newer version keep it: Android never downgrades. Fix forward with a higher `versionCode`.

## Remote switches (no release needed)
| Variable | Effect |
|---|---|
| `ANDROID_LATEST_VERSION_CODE` | Newer than the installed version: the app offers the update |
| `ANDROID_MIN_VERSION_CODE` | Older than this: the app blocks until updated |
| `ANDROID_APK_URL`, `ANDROID_APK_SHA256` | The APK to download, and its fingerprint (no fingerprint, no install) |
| `ANDROID_STORE_URL` | Once on Play: the download page links to Play instead |
| `APP_NOTICE` | A one-line message at the top of the app for everyone |
| `APP_FEATURES` | Comma-separated remote switches |

## Later: Google Play
1. Create the Play Console account (USD 25).
2. Create the app and **use the same key** (Play App Signing → "Use existing app signing key"), so people
   who installed from the website can switch to Play updates.
3. Build the Play bundle:
   ```bash
   ./gradlew bundlePlayRelease -PappId=<id> -PsiteUrl=https://app.<domain> -PapiUrl=https://api.<domain> \
     -PversionCode=<n> -PversionName=<x.y.z>
   ```
4. Store listing, privacy policy (D5), data safety form (account email and name, client contact details, no
   data sold, encrypted in transit), content rating.
5. Internal testing, then production with a staged rollout (10% → 50% → 100%).
6. Set `ANDROID_STORE_URL`, so the download page points to Play.
