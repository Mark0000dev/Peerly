import assert from 'node:assert/strict';
import { constants, accessSync, mkdirSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { resolve, join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { execFileSync, spawnSync } from 'node:child_process';

export const acceptedSdkLicense = '9002c006f4b8d9a16e715a9fa4df30ddb8abf9d9';
const hash = (bytes) => createHash('sha256').update(bytes).digest('hex');
const variants = {
  production: { id: 'dev.alekseiorlov.peerly', origin: 'https://peerly.aleksei-orlov.dev' },
  staging: {
    id: 'dev.alekseiorlov.peerly.staging',
    origin: 'https://peerly-staging.aleksei-orlov.dev',
  },
};
const nonempty = (path) =>
  assert.ok(statSync(path).size > 0, `Required preinstalled SDK file empty: ${path}`);

export function preflightSdk(sdk) {
  assert.ok(sdk, 'ANDROID_HOME must name an existing SDK; no install/download fallback');
  const root = resolve(sdk);
  const licensePath = join(root, 'licenses/android-sdk-license');
  const license = readFileSync(licensePath);
  assert.ok(
    license.toString('utf8').split(/\r?\n/).includes(acceptedSdkLicense),
    'SDK36 license is not already recorded as accepted; no terms will be accepted',
  );
  const platform = join(root, 'platforms/android-36');
  const tools = join(root, 'build-tools/36.0.0');
  nonempty(join(platform, 'android.jar'));
  assert.match(
    readFileSync(join(platform, 'source.properties'), 'utf8'),
    /^AndroidVersion\.ApiLevel\s*=\s*36\s*$/m,
  );
  assert.match(
    readFileSync(join(tools, 'source.properties'), 'utf8'),
    /^Pkg\.Revision\s*=\s*36\.0\.0\s*$/m,
  );
  for (const path of [join(platform, 'package.xml'), join(tools, 'package.xml')]) {
    assert.match(readFileSync(path, 'utf8'), /<uses-license\s+ref="android-sdk-license"\s*\/?\s*>/);
  }
  for (const tool of ['aapt2', 'apksigner']) accessSync(join(tools, tool), constants.X_OK);
  return {
    root,
    platform: 'android-36',
    buildTools: '36.0.0',
    licensePath,
    licenseSha256: hash(license),
    acceptedLicenseSha1: acceptedSdkLicense,
  };
}

// Parse aapt2's actual binary-manifest dump. This helper alone is not APK acceptance.
export function manifestTree(text) {
  const root = { name: 'root', attributes: {}, children: [], indent: -1 };
  const stack = [root];
  for (const line of text.split('\n')) {
    const element = /^(\s*)E: ([\w.-]+)(?:\s|$)/.exec(line);
    if (element) {
      const node = { name: element[2], attributes: {}, children: [], indent: element[1].length };
      while (stack.at(-1).indent >= node.indent) stack.pop();
      stack.at(-1).children.push(node);
      stack.push(node);
      continue;
    }
    const attribute = /^\s*A: ([\w:.-]+)(?:\(0x[\da-fA-F]+\))?=(.*)$/.exec(line);
    if (attribute) {
      const quoted = /^("(?:[^"\\]|\\.)*")/.exec(attribute[2]);
      // Retain non-string/resource attributes too, so extra wake constraints fail.
      stack.at(-1).attributes[attribute[1]] = quoted ? JSON.parse(quoted[1]) : attribute[2];
    }
  }
  return root;
}

export function verifyManifest(text, identifier) {
  const roots = manifestTree(text).children;
  assert.equal(roots.length, 1);
  const manifest = roots[0];
  assert.equal(manifest.name, 'manifest');
  assert.equal(manifest.attributes.package, identifier);
  const apps = manifest.children.filter((node) => node.name === 'application');
  assert.equal(apps.length, 1);
  const activities = apps[0].children.filter(
    (node) =>
      node.name === 'activity' &&
      node.attributes['android:name'] === 'dev.alekseiorlov.peerly.MainActivity',
  );
  assert.equal(activities.length, 1);
  const wakeFilters = activities[0].children.filter(
    (node) =>
      node.name === 'intent-filter' &&
      node.children.some(
        (child) =>
          child.name === 'category' &&
          child.attributes['android:name'] === 'android.intent.category.BROWSABLE',
      ),
  );
  assert.equal(wakeFilters.length, 1);
  const filter = wakeFilters[0];
  assert.ok(
    filter.children.some(
      (child) =>
        child.name === 'action' &&
        child.attributes['android:name'] === 'android.intent.action.VIEW',
    ),
  );
  assert.ok(
    filter.children.some(
      (child) =>
        child.name === 'category' &&
        child.attributes['android:name'] === 'android.intent.category.DEFAULT',
    ),
  );
  const data = filter.children.filter((node) => node.name === 'data');
  assert.equal(data.length, 1);
  assert.deepEqual(data[0].attributes, {
    'android:scheme': identifier,
    'android:host': 'auth',
    'android:path': '/complete',
  });
}

export function verifyPackagedConfig(config, variant) {
  const expected = variants[variant];
  assert.ok(expected, 'Unknown variant');
  assert.equal(config.appId, expected.id);
  assert.equal(config.plugins?.PeerlyTransport?.apiOrigin, expected.origin);
  assert.equal(config.plugins?.PeerlyTransport?.wakeUrl, `${expected.id}://auth/complete`);
  assert.equal(config.loggingBehavior, 'none');
  assert.equal(config.plugins?.CapacitorHttp?.enabled, false);
  assert.equal(config.plugins?.CapacitorCookies?.enabled, false);
  assert.deepEqual(config.server ?? {}, {});
}

function verifyApk(sdk, variant, apk, output) {
  const expected = variants[variant];
  assert.ok(expected, 'Unknown variant');
  const bytes = readFileSync(apk);
  assert.ok(bytes.length > 0 && bytes.length <= 100 * 1024 * 1024);
  const run = (tool, args) =>
    execFileSync(tool, args, { encoding: 'utf8', maxBuffer: 4 * 1024 * 1024 });
  const files = run('unzip', ['-Z1', apk]).trim().split('\n');
  assert.equal(files.filter((name) => name === 'assets/capacitor.config.json').length, 1);
  assert.ok(
    files.some((name) => /^classes\d*\.dex$/.test(name)),
    'Compiled DEX missing',
  );
  assert.ok(
    !files.some((name) => /^META-INF\/.*\.(SF|RSA|DSA|EC)$/i.test(name)),
    'Unexpected v1 signing material',
  );
  // Signing-block footer immediately precedes the ZIP central directory.
  let eocd = -1;
  for (let i = bytes.length - 22; i >= Math.max(0, bytes.length - 65557); i--) {
    if (
      bytes.readUInt32LE(i) === 0x06054b50 &&
      i + 22 + bytes.readUInt16LE(i + 20) === bytes.length
    ) {
      eocd = i;
      break;
    }
  }
  assert.ok(eocd >= 0, 'APK ZIP directory missing');
  const directory = bytes.readUInt32LE(eocd + 16);
  assert.ok(directory > 16 && directory < eocd);
  assert.notEqual(
    bytes.subarray(directory - 16, directory).toString('ascii'),
    'APK Sig Block 42',
    'APK unexpectedly signed',
  );
  const tools = join(sdk.root, 'build-tools/36.0.0');
  const signature = spawnSync(join(tools, 'apksigner'), ['verify', '--verbose', apk], {
    encoding: 'utf8',
    maxBuffer: 1024 * 1024,
  });
  assert.equal(
    signature.status,
    1,
    'Expected an unsigned APK, not successful signature verification or a tool failure',
  );
  assert.match(signature.stdout + signature.stderr, /DOES NOT VERIFY/);
  const manifest = run(join(tools, 'aapt2'), [
    'dump',
    'xmltree',
    '--file',
    'AndroidManifest.xml',
    apk,
  ]);
  verifyManifest(manifest, expected.id);
  const config = JSON.parse(run('unzip', ['-p', apk, 'assets/capacitor.config.json']));
  verifyPackagedConfig(config, variant);
  mkdirSync(output, { recursive: true });
  writeFileSync(join(output, `${variant}-manifest.txt`), manifest);
  writeFileSync(
    join(output, `${variant}-receipt.json`),
    JSON.stringify(
      {
        variant,
        applicationId: expected.id,
        apiOrigin: expected.origin,
        wakeUrl: `${expected.id}://auth/complete`,
        artifactSha256: hash(bytes),
        artifactBytes: bytes.length,
        unsigned: true,
        manifestVerifiedFromApk: true,
        configVerifiedFromApk: true,
        platformRuntimeAcceptance: false,
      },
      null,
      2,
    ) + '\n',
  );
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const [mode, sdk, ...args] = process.argv.slice(2);
  if (mode === 'preflight') {
    const record = preflightSdk(sdk);
    mkdirSync(args[0], { recursive: true });
    writeFileSync(join(args[0], 'sdk-preflight.json'), JSON.stringify(record, null, 2) + '\n');
  } else if (mode === 'verify') {
    const before = JSON.parse(readFileSync(join(args[2], 'sdk-preflight.json'), 'utf8'));
    const current = preflightSdk(sdk);
    assert.deepEqual(current, before, 'SDK/license record changed during build');
    verifyApk(current, args[0], args[1], args[2]);
  } else throw new Error('Expected preflight or verify; no installer exists in this tool');
}
