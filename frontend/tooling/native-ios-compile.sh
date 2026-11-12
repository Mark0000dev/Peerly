#!/usr/bin/env bash
# Actual unsigned compilation only; run from frontend on macOS with Xcode 26+.
set -euo pipefail
if [[ "$(uname -s)" != Darwin ]]; then
  echo 'A macOS Xcode runner is required; no native compilation was performed.' >&2
  exit 1
fi
node --eval 'if (Number(process.versions.node.split(".")[0]) !== 24) process.exit(1)'
xcodebuild -version
xcrun --sdk iphonesimulator --find swiftc
npm run build
# One canonical generated config; iOS target settings own the variant origin/ID.
PEERLY_NATIVE_VARIANT=production npx --no-install cap sync ios
for native_scheme in Peerly Peerly-Staging; do
  native_configuration=Release
  native_identifier=dev.alekseiorlov.peerly
  native_origin=https://peerly.aleksei-orlov.dev
  if [[ "$native_scheme" == Peerly-Staging ]]; then
    native_configuration=StagingRelease
    native_identifier=dev.alekseiorlov.peerly.staging
    native_origin=https://peerly-staging.aleksei-orlov.dev
  fi
  native_derived="$PWD/ios/App/build/$native_scheme"
  mkdir -p "$native_derived"
  # A stale result bundle must fail, rather than being mistaken for this compile.
  test ! -e "$native_derived/compile.xcresult"
  xcodebuild -resolvePackageDependencies -project ios/App/App.xcodeproj -scheme "$native_scheme"
  xcodebuild -project ios/App/App.xcodeproj -scheme "$native_scheme" \
    -sdk iphonesimulator -destination 'generic/platform=iOS Simulator' \
    -configuration "$native_configuration" \
    -derivedDataPath "$native_derived" -resultBundlePath "$native_derived/compile.xcresult" \
    CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO build
  native_app="$native_derived/Build/Products/$native_configuration-iphonesimulator/App.app"
  test -s "$native_app/App"
  file "$native_app/App" | tee "$native_derived/variant-receipt.txt"
  test "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$native_app/Info.plist")" = "$native_identifier"
  test "$(/usr/libexec/PlistBuddy -c 'Print :PeerlyAPIOrigin' "$native_app/Info.plist")" = "$native_origin"
  test "$(/usr/libexec/PlistBuddy -c 'Print :PeerlyWakeURL' "$native_app/Info.plist")" = "$native_identifier://auth/complete"
  test "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleURLTypes:0:CFBundleURLSchemes:0' "$native_app/Info.plist")" = "$native_identifier"
  printf 'Unsigned simulator compile succeeded: %s %s\n' "$native_scheme" "$native_identifier" \
    | tee -a "$native_derived/variant-receipt.txt"
done
