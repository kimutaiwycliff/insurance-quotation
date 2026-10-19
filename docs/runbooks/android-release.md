# Runbook: releasing the Android app

## One-time setup
1. **Choose the application ID** with the product name (D7), e.g. `ke.co.<name>.app`. It can **never change**
   after the first upload. Until then builds use the placeholder `app.brokeros.android`.
2. **Create a Google Play Console account** (one-time USD 25, needs a card).
   - Create the app.
   - Accept **Play App Signing**: Google keeps the signing key, and you keep only an upload key.
3. **Create the upload key** on your computer, outside the repository:
   ```bash
   keytool -genkeypair -v -keystore upload.jks -alias upload -keyalg RSA -keysize 4096 -validity 10000
   ```
   Save `upload.jks` and both passwords in your password manager.
4. **Fill in the Play Console requirements:**
   - store listing;
   - privacy policy URL (D5, the lawyer);
   - data safety form: account email and name, client contact details, no data sold, data encrypted in transit;
   - content rating;
   - target audience (adults, business).

## Each release
1. **Build the bundle** (Play needs an `.aab`):
   ```bash
   cd apps/android
   export ANDROID_UPLOAD_KEYSTORE=/path/to/upload.jks ANDROID_UPLOAD_KEYSTORE_PASSWORD=… \
          ANDROID_UPLOAD_KEY_ALIAS=upload ANDROID_UPLOAD_KEY_PASSWORD=…
   ./gradlew bundleRelease -PappId=<application id> -PsiteUrl=https://app.<domain> \
     -PapiUrl=https://api.<domain> -PversionCode=<next number> -PversionName=0.2.0
   ```
   The bundle is at `app/build/outputs/bundle/release/app-release.aab`. `versionCode` must go up with every
   upload.
2. **Upload to Internal testing** first. Install from the testing link and check:
   - sign-in, including two-factor;
   - Home;
   - client search, Call and WhatsApp;
   - sign-out.
3. **Promote to Production with a staged rollout.**
   - Start at 10%. Watch Play Console → Android vitals (crashes, ANRs) for a day, then 50%, then 100%.
   - If something is wrong, halt the rollout in Play Console. Users who already updated stay on it; fix
     forward with the next version.

## "Over the air" switches (no release needed)
They're set in the server's `.env`, then `deploy/bin/deploy.sh` (or just restart the API).

| Variable | Effect |
|---|---|
| `ANDROID_LATEST_VERSION_CODE` | Newer than the installed version: the app offers to update (downloads in the background) |
| `ANDROID_MIN_VERSION_CODE` | Older than this: the app blocks until updated (security fixes, breaking API changes) |
| `ANDROID_STORE_URL` | Play listing, opened when Play's in-app update isn't available (e.g. side-loaded) |
| `APP_NOTICE` | A one-line message at the top of the app for everyone |
| `APP_FEATURES` | Comma-separated remote switches the app checks (none are used yet) |

Raise `ANDROID_MIN_VERSION_CODE` only after the new version is at 100% on Play, or people will be told to
update before Play offers it to them.
