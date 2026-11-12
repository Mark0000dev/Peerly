#!/usr/bin/env bash
# Existing hosted SDK only. No sdkmanager, SDK installer, license acceptance or fallback.
set -euo pipefail
native_sdk="${ANDROID_HOME:?Preinstalled ANDROID_HOME required; no SDK download fallback}"
if [[ -n "${ANDROID_SDK_ROOT:-}" && "$ANDROID_SDK_ROOT" != "$native_sdk" ]]; then
  echo 'ANDROID_HOME/ANDROID_SDK_ROOT disagree; refusing to select another SDK.' >&2
  exit 1
fi
native_receipts="$PWD/android/native-evidence"
node tooling/native-android-verify.mjs preflight "$native_sdk" "$native_receipts"
if [[ "${1:-}" == --preflight-only ]]; then exit 0; fi
if [[ "$#" != 0 ]]; then echo 'Unknown compile option.' >&2; exit 1; fi
export JAVA_HOME="${JAVA_HOME_21_X64:?Preinstalled runner Java21 required; no JDK installer}"
export PATH="$JAVA_HOME/bin:$PATH"
java -version
npm run build
PEERLY_NATIVE_VARIANT=production npx --no-install cap sync android
# No machine-local SDK path is shipped. Gradle resolves the preflighted ANDROID_HOME.
test ! -e android/local.properties
(
  cd android
  ./gradlew --no-daemon --console=plain -Pandroid.builder.sdkDownload=false --write-locks \
    :app:assembleProductionRelease :app:assembleStagingRelease
)
for native_variant in production staging; do
  native_apk="android/app/build/outputs/apk/$native_variant/release/app-$native_variant-release-unsigned.apk"
  test -s "$native_apk"
  node tooling/native-android-verify.mjs verify "$native_sdk" "$native_variant" "$native_apk" "$native_receipts"
done
