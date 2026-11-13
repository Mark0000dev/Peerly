# Native authentication and release runbook

Peerly packages the web interface with Capacitor and uses the server's Google login
and university-email verification. Web authentication remains same-origin. Native
releases require unsigned platform compilation and separate signed-device acceptance;
passing source tests or compiling an app does not establish successful native login.

## Application identities and origins

| Variant    | App/bundle ID                     | API origin                                 | Exact wake URL                                    |
| ---------- | --------------------------------- | ------------------------------------------ | ------------------------------------------------- |
| Production | `dev.alekseiorlov.peerly`         | `https://peerly.aleksei-orlov.dev`         | `dev.alekseiorlov.peerly://auth/complete`         |
| Staging    | `dev.alekseiorlov.peerly.staging` | `https://peerly-staging.aleksei-orlov.dev` | `dev.alekseiorlov.peerly.staging://auth/complete` |

The wake URL contains no query, fragment, verifier, authorization code or session.
Android flavors and iOS build configurations select the actual application identity.
Android's staging assets override the production transport configuration. iOS reads
its API origin and wake URL from build settings in Info.plist. The native runtime
checks that the actual package identity, API origin and wake URL form one valid variant.

The packaged WebView page origins are `https://localhost` on Android and
`capacitor://localhost` on iOS. These are distinct from the remote API origin and wake
scheme. Keep hostname/scheme defaults, packaged web assets and disabled global
Capacitor Http/Cookies patches. Do not use `server.url` or broaden navigation for Google.

## Login with separate cookie jars

The external browser and native cookie store are independent. Login must not depend
on copying cookies between them.

1. The login action clears the native session, advances its transport epoch and
   retires private queries. It creates a random attempt UUID and S256 verifier in
   memory and registers the App wake listener. This step makes no HTTP request that
   would issue a browser-binding cookie into the native jar.
2. Capacitor Browser opens the fixed API's `/api/v1/auth/native/start` URL with the
   UUID and non-secret S256 challenge. The verifier stays in memory. The external
   browser makes this initial GET and receives the login-binding cookie and native
   marker in its own jar. Google authentication runs in that external browser.
3. The server's existing Google callback validates the external browser's cookie,
   state and provider response. It binds a short-lived provisional session digest to
   the attempt. An independent existing browser web session is preserved. A clean
   return page offers the exact fixed wake link without auth data.
4. The native jar can still be empty. Native HTTP posts the UUID and verifier in a
   JSON body to `/api/v1/auth/native/exchange`. The server checks proof, expiry and
   live identity, retrieves the callback-bound provisional session server-side,
   consumes the attempt once, revokes the provisional session and issues a normal
   session only through Secure, HttpOnly, host-only Set-Cookie. The external login
   cookie and marker are not required in the native jar.
5. The native adapter confirms its session cookie was installed before reporting
   success. The application fetches canonical `/api/v1/me`; Google issuer/subject
   login does not establish APU membership. University-email code verification remains
   a separate server-validated requirement for student features.

Do not request native start through HttpClient and assume its cookie reaches Safari
or Custom Tabs. Sign-in expires after five minutes. Cancellation, view retirement or
actor replacement must abort the attempt. A cold launch cannot recover an in-memory
verifier; it offers a fresh sign-in rather than reconstructing authority from a wake URL.

## Transport, media and security

Android registers `PeerlyTransportPlugin` in MainActivity and uses OkHttp with Android
CookieManager. iOS registers it through PeerlyBridgeViewController and uses ephemeral
URLSession streaming with the owning WebView's WKHTTPCookieStore. API HTTP, SSE and
binary media use the same native session jar.

The adapter permits only the fixed HTTPS API host and relative `/api/v1` paths.
Google/start navigation remains in Browser. Automatic cookie handling, redirects,
credential caches and native logging are disabled. Cookies and raw Set-Cookie headers
never become JS return values. Do not log credentials, proof values or full callback
URLs, or persist them in JS storage.

Cookie changes serialize with transport epochs. Late responses and cookie writes
from retired epochs are rejected. Unsubscribe cancels the physical network request;
logout retires cookies and epoch before publishing success. Mutations are not replayed.
Limits are 16 MiB per ordinary response, 1 MiB per stream and 16 active requests, with
bounded connection, idle and total time. The existing client owns SSE reconnection.

Own-profile images use native binary reads and owned Blob URLs rather than raw
cross-site authenticated `<img>` URLs. Other media consumers already use binary
HttpClient reads. Actor, authority, epoch and view changes cancel reads and retire
Blob URLs after DOM retirement. Web builds retain ordinary image-source behavior.

Signed object uploads bypass native API credential transport. The upload client uses
FormData POST without custom headers and with credentials omitted. CORS must allow
both native page origins on the existing upload POST rule while preserving required
web origins. Do not add wildcards, ACL changes or unrelated headers/methods to diagnose
native upload failures.

An OPTIONS403 response alone does not establish that a signed FormData upload fails;
the application makes no explicit OPTIONS call, although a WebView may initiate
preflight. Acceptance requires observing the real WebView Origin, a valid signed POST
and readable response under CORS on each platform. Configured origins are not device
upload proof. Never include signed upload fields or URLs in diagnostic logs.

## Server configuration and schema

Use the existing web-auth settings: `DATABASE_URL`, `AUTHENTICATION__CLIENT_ID`,
`AUTHENTICATION__CLIENT_SECRET`, `AUTHENTICATION__PUBLIC_ORIGIN`,
`AUTHENTICATION__ENVELOPE_KEY`, `AUTHENTICATION__BROWSER_SIGNING_KEY` and
`AUTHENTICATION__CODE_KEY`. Keep secret values in the deployment's secret mechanism.
Native authentication introduces no separate Google native-client credential or
native-specific server secret. The public origin must match the selected API origin.

Schema `0061_native_login` follows `0060_report_triage` and provides the native attempt
table and expiry index. Native start, exchange and native-marked callbacks require
that schema. A successful SELECT1 readiness probe is insufficient: deployment must
verify the reviewed schema target and compatible binary/API/configuration explicitly.
There is no native-only server disable flag; disabling all authentication is not a
scoped native rollback procedure.

### Retention and rollback

MVP retains native attempts, including expired, consumed and cancelled records, and
referenced source sessions, including expired or revoked sessions. There is no new
purge job or attempt-first deletion requirement. Expiry limits authentication authority;
it does not promise record deletion. Retained records never bypass current session,
identity or single-use proof checks.

The RESTRICT foreign key from attempt source digest to session digest intentionally
preserves retained lineage. Current runtime has no session DELETE/purger. A synthetic
purge test demonstrates that the FK rejects deletion of referenced sessions; it is
integrity evidence, not a demonstrated runtime bug or an additional release blocker.
Its test-only attempt-first deletion is not an approved production cleanup policy.

Any future purger requires a separately coordinated retention design, relationship
and lineage assessment, concurrency/rollback plan and actual tests. Do not introduce
CASCADE, SET NULL, early attempt deletion or automatic GC as an incidental fix.

Cross-version rollout and rollback still require explicit compatibility proof. A
quiesced downgrade drops attempt records but does not undo issued sessions or restore
revoked provisional authority. The availability of a downgrade is not approval to
erase retained lineage or run it under active native traffic. Use a reviewed rollback
procedure; do not infer whole-binary compatibility from additive DDL or session-reader
checks alone.

## Unsigned builds and CI

Use Node and npm versions pinned by `.nvmrc` and `package.json`, install the lockfile
with `npm ci`, and retain the repository dependency patches. Use a clean build workspace.
The standalone `capacitor.config.ts` typecheck runs in Node: its `tsc --ignoreConfig`
invocation must explicitly include `--types node`, using the installed `@types/node`
declarations. This supplies the Node `process.env` types used by the variant selector.
Run `npm run typecheck` with that explicit config-check flag as part of source validation.

For the standalone check from `frontend/`:

```sh
npx --no-install tsc --ignoreConfig --strict --noEmit --skipLibCheck \
  --module nodenext --moduleResolution nodenext --target es2022 \
  --types node capacitor.config.ts
```

Canonical synchronization uses `PEERLY_NATIVE_VARIANT=production`; the platform
projects then select production or staging through their flavors/configurations.

The [unsigned workflow](../.github/workflows/native-ios-unsigned.yml) runs on matching
pull requests and supports manual reruns. It checks out the exact candidate, uses
pinned actions and has no signing/store secrets or deployment step. Both platform jobs
must produce real compile evidence before a native change is accepted for merge.
Source checks, synthetic tool fixtures and an unexecuted workflow are not compilation.

### Android

Required: already-installed Android SDK36, Build Tools36.0.0 and Java21. `ANDROID_HOME`
must name that SDK; `ANDROID_SDK_ROOT`, when present, must agree. The compile helper
uses `JAVA_HOME_21_X64` for the installed Java21 directory and rejects machine-local
`android/local.properties` so SDK selection remains explicit.

Preflight requires existing Python3 and reads each installed platform/build-tools
`package.xml` with bounded stdlib XML parsing. DTD/entity declarations and external
resolution are forbidden. Every referenced license must have exact embedded text;
its UTF-8 SHA1 must already occur as a complete line in the corresponding existing
`$ANDROID_HOME/licenses/<license-id>` record. There is no global online-license hash
or old-hash allowlist. Metadata, properties and license-record SHA256s bind the SDK
snapshot checked again after compilation.

The safe `android/native-evidence/sdk-preflight-diagnostic.json` is written even on
rejection. It reports package/license IDs, metadata/content/record hashes and fixed
error codes, without raw license text or URLs. Missing metadata/text/reference,
mismatched acceptance or wrong installed versions fail closed. Preflight does not
authorize accepting terms, writing records or installing missing packages. There is
no SDK installer or download fallback; environment owners handle any required
installation/license decision separately.

From `frontend/`:

```sh
bash tooling/native-android-compile.sh --preflight-only
bash tooling/native-android-compile.sh
```

The helper builds web assets, synchronizes Android, and runs both real release
assemblies with SDK download disabled and no release signing configuration. All Android
modules use Build Tools36.0.0. The verifier reads each actual APK's binary manifest and
packaged Capacitor config, checking package ID, fixed API origin, exact wake route,
compiled DEX and unsigned status. SDK license bytes must remain unchanged.

Inspect `android/native-evidence/`, the actual unsigned APKs, compile logs and generated
Gradle locks retained by CI. Review dependency locks before a release. An unsigned
release APK is not an installable signed-device or distribution artifact.

### iOS

Required: macOS with Xcode26.3, its iOS Simulator SDK and the pinned Node/npm dependencies.
The CI job selects the explicit Xcode installation rather than the runner's default.
Use a fresh derived-data/result-bundle location; the helper rejects stale result bundles.

From `frontend/`:

```sh
bash tooling/native-ios-compile.sh
```

The helper synchronizes iOS and invokes real xcodebuild for `Peerly` and
`Peerly-Staging`, with signing disabled. It requires actual app executables and built
Info.plist values matching each identifier, API origin and wake registration. Inspect
xcresult bundles, compile logs and variant receipts. Linux source checks cannot
substitute for Xcode compilation.

## Installation, tests and release acceptance

Use an Android emulator or approved device and an iOS Simulator or approved iPhone.
Android device installation requires suitable development/test signing; iPhone
installation requires an approved team, provisioning and signing setup. Keep signing
keys and profiles outside the repository and logs. Assign distribution ownership and
versioning before preparing store or external-test builds; unsigned CI has no store role.

Run the Android CookieManager instrumentation test on an available emulator/device
with `:app:connectedStagingDebugAndroidTest`. The WKHTTPCookieStore test source must be
attached to an XCTest target before it is an executable iOS test gate. Those cookie
visibility tests do not by themselves test the production plugin's HTTPS transport.

Maintain real PostgreSQL tests for distinct external/native HTTP clients, seeded
schema upgrades, proof expiry/replay/revocation and retained FK behavior. A controlled
Google boundary verifies server protocol, not provider acceptance. Check schema changes
on disposable isolated databases; never reset shared application data for these tests.

For each platform and variant, record the running artifact identity and verify:

- Actual platform jar installation/readback and normal `/me`, CSRF and authenticated writes.
- JPEG/media loading, split SSE, abort, logout, late-cookie epoch fencing and relaunch.
- External-browser Google login, exact wake handling, cancellation and separate jars.
- Actual APU mailbox-code delivery and verification without membership placeholders.
- Valid signed object upload and response CORS using the actual WebView Origin.
- Background/foreground, actor replacement and expired/revoked/banned/deleted authority.

Compilation, a browser opening, unit mocks, configured CORS or SMTP250 are not proof
of device interoperability, inbox delivery or production readiness. Device/provider
acceptance remains required for the actual shipping artifact.

## Primary references

- [Google OAuth policy](https://developers.google.com/identity/protocols/oauth2/policies) and [native application guidance](https://developers.google.com/identity/protocols/oauth2/native-app).
- Capacitor [Browser](https://capacitorjs.com/docs/apis/browser), [App](https://capacitorjs.com/docs/apis/app), [Http](https://capacitorjs.com/docs/apis/http), [Cookies](https://capacitorjs.com/docs/apis/cookies) and [environment setup](https://capacitorjs.com/docs/getting-started/environment-setup).
- [Android CookieManager](https://developer.android.com/reference/android/webkit/CookieManager), [WKHTTPCookieStore](https://developer.apple.com/documentation/webkit/wkhttpcookiestore) and [URLSession delegate](https://developer.apple.com/documentation/foundation/urlsessiondatadelegate).
- [AAPT2](https://developer.android.com/tools/aapt2), [apksigner](https://developer.android.com/tools/apksigner) and [SDK repository metadata](https://dl.google.com/android/repository/repository2-1.xml).
