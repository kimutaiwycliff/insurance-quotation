#!/usr/bin/env bash
# Creates the key that signs every release of the Android app (run once, ever).
# Phones only accept an update signed with the same key as the installed app: lose it and everyone must
# uninstall and reinstall. Keep the file and both passwords in your password manager and a second safe place.
# Usage: apps/android/scripts/new-signing-key.sh [path]   (default: ~/brokeros-signing/release.jks)
set -euo pipefail
target="${1:-$HOME/brokeros-signing/release.jks}"
if [[ -e "$target" ]]; then
  echo "$target already exists; not overwriting it." >&2
  exit 1
fi
mkdir -p "$(dirname "$target")"
chmod 700 "$(dirname "$target")"
keytool -genkeypair -v -keystore "$target" -alias release -keyalg RSA -keysize 4096 -validity 10000
chmod 600 "$target"
echo
echo "Created $target (alias: release). Back it up now, with its passwords."
echo "Never put it in the repository. scripts/release-apk.sh uses it through these variables:"
echo "  export ANDROID_UPLOAD_KEYSTORE=$target ANDROID_UPLOAD_KEY_ALIAS=release"
echo "  export ANDROID_UPLOAD_KEYSTORE_PASSWORD=... ANDROID_UPLOAD_KEY_PASSWORD=..."
