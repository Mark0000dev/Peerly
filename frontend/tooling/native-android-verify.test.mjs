import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import {
  acceptedSdkLicense,
  preflightSdk,
  verifyManifest,
  verifyPackagedConfig,
} from './native-android-verify.mjs';

// Synthetic metadata/unit checks only: no SDK install, compiler, real APK or device proof.
function fixtureSdk() {
  const root = mkdtempSync(join(tmpdir(), 'peerly-sdk-static-'));
  const files = {
    'licenses/android-sdk-license': acceptedSdkLicense + '\n',
    'platforms/android-36/android.jar': 'synthetic file, never a compiler input',
    'platforms/android-36/source.properties': 'AndroidVersion.ApiLevel=36\n',
    'platforms/android-36/package.xml': '<uses-license ref="android-sdk-license"/>',
    'build-tools/36.0.0/source.properties': 'Pkg.Revision=36.0.0\n',
    'build-tools/36.0.0/package.xml': '<uses-license ref="android-sdk-license"/>',
    'build-tools/36.0.0/aapt2': 'synthetic file, never executed',
    'build-tools/36.0.0/apksigner': 'synthetic file, never executed',
  };
  for (const [path, contents] of Object.entries(files)) {
    const target = join(root, path);
    mkdirSync(join(target, '..'), { recursive: true });
    writeFileSync(target, contents, {
      mode: path.endsWith('/aapt2') || path.endsWith('/apksigner') ? 0o700 : 0o600,
    });
  }
  return root;
}
const manifest = (id) => `N: android=http://schemas.android.com/apk/res/android
  E: manifest (line=1)
    A: package="${id}" (Raw: "${id}")
    E: application (line=2)
      E: activity (line=3)
        A: android:name(0x01010003)="dev.alekseiorlov.peerly.MainActivity"
        E: intent-filter (line=4)
          E: action (line=5)
            A: android:name(0x01010003)="android.intent.action.VIEW"
          E: category (line=6)
            A: android:name(0x01010003)="android.intent.category.DEFAULT"
          E: category (line=7)
            A: android:name(0x01010003)="android.intent.category.BROWSABLE"
          E: data (line=8)
            A: android:scheme(0x01010027)="${id}"
            A: android:host(0x01010028)="auth"
            A: android:path(0x0101002a)="/complete"
`;
for (const suffix of ['', '.staging'])
  test('checks aapt2 metadata for the exact variant ' + suffix, () => {
    const id = 'dev.alekseiorlov.peerly' + suffix;
    verifyManifest(manifest(id), id);
    assert.throws(() =>
      verifyManifest(manifest(id) + '            A: android:port(0x01010029)=@0x7f010001\n', id),
    );
    assert.throws(() => verifyManifest(manifest(id).replace('="auth"', '="other"'), id));
    assert.throws(() =>
      verifyManifest(manifest(id).replace('="/complete"', '="/complete?token=x"'), id),
    );
    assert.throws(() => verifyManifest(manifest(id), id + '.wrong'));
    assert.throws(() =>
      verifyManifest(
        manifest(id).replace('android:path(0x0101002a)', 'android:pathPrefix(0x0101002a)'),
        id,
      ),
    );
  });
test('rejects cross-variant or patched packaged configuration', () => {
  const config = {
    appId: 'dev.alekseiorlov.peerly',
    loggingBehavior: 'none',
    plugins: {
      PeerlyTransport: {
        apiOrigin: 'https://peerly.aleksei-orlov.dev',
        wakeUrl: 'dev.alekseiorlov.peerly://auth/complete',
      },
      CapacitorHttp: { enabled: false },
      CapacitorCookies: { enabled: false },
    },
  };
  verifyPackagedConfig(config, 'production');
  assert.throws(() => verifyPackagedConfig(config, 'staging'));
  assert.throws(() =>
    verifyPackagedConfig({ ...config, server: { url: 'https://foreign.invalid' } }, 'production'),
  );
  assert.throws(() =>
    verifyPackagedConfig(
      { ...config, plugins: { ...config.plugins, CapacitorHttp: { enabled: true } } },
      'production',
    ),
  );
});
test('fails closed for missing SDK without attempting installation', () => {
  assert.throws(() => preflightSdk(''));
  assert.throws(() => preflightSdk('/nonexistent/peerly-sdk-static-fixture'));
});
test('requires preexisting exact license record and installed package/tool metadata', () => {
  const root = fixtureSdk();
  try {
    assert.equal(preflightSdk(root).buildTools, '36.0.0');
    writeFileSync(
      join(root, 'licenses/android-sdk-license'),
      '24333f8a63b6825ea9c5514f83c2829b004d1fee\n',
    );
    assert.throws(() => preflightSdk(root), /not already recorded as accepted/);
    writeFileSync(join(root, 'licenses/android-sdk-license'), acceptedSdkLicense + '\n');
    rmSync(join(root, 'platforms/android-36/android.jar'));
    assert.throws(() => preflightSdk(root));
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
