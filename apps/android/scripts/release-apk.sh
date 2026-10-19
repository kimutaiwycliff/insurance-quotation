#!/usr/bin/env bash
# Builds a signed APK of the direct-download app for your server, and prints how to publish it.
# Usage: apps/android/scripts/release-apk.sh <domain> <versionCode> <versionName>
#   e.g. apps/android/scripts/release-apk.sh 129-146-10-20.sslip.io 3 0.3.0
# Needs JDK 17+, the Android SDK and the signing key (scripts/new-signing-key.sh) in ANDROID_UPLOAD_* variables.
set -euo pipefail
cd "$(dirname "$0")/.."

domain="${1:?usage: release-apk.sh <domain> <versionCode> <versionName>}"
code="${2:?versionCode (a whole number, higher than the last release)}"
name="${3:?versionName, e.g. 0.3.0}"
: "${ANDROID_UPLOAD_KEYSTORE:?set ANDROID_UPLOAD_KEYSTORE (and the other ANDROID_UPLOAD_* variables)}"
[[ "$code" =~ ^[0-9]+$ ]] || { echo "versionCode must be a whole number" >&2; exit 1; }

./gradlew assembleDirectRelease --console=plain \
  -PversionCode="$code" -PversionName="$name" \
  -PsiteUrl="https://app.$domain" -PapiUrl="https://api.$domain" \
  ${APP_ID:+-PappId="$APP_ID"}

apk="app/build/outputs/apk/direct/release/app-direct-release.apk"
[[ -f "$apk" ]] || { echo "No signed APK at $apk (are the ANDROID_UPLOAD_* variables right?)" >&2; exit 1; }
mkdir -p dist
out="dist/brokeros-$name.apk"
cp "$apk" "$out"
sha=$(shasum -a 256 "$out" | cut -d' ' -f1)

cat <<DONE

Built $out
SHA-256 $sha

Publish it:
  scp $out ubuntu@<vm-ip>:/opt/brokeros/deploy/downloads/
  ssh ubuntu@<vm-ip> 'cd /opt/brokeros && cp deploy/downloads/brokeros-$name.apk deploy/downloads/brokeros-latest.apk'

Then set these in /opt/brokeros/.env on the VM and run deploy/bin/deploy.sh (or restart the API):
  ANDROID_APK_URL=/downloads/brokeros-$name.apk
  ANDROID_APK_SHA256=$sha
  ANDROID_LATEST_VERSION_CODE=$code
Phones then offer the update; https://app.$domain/download always offers the newest.
DONE
