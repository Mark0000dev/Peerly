import { lstatSync, opendirSync, realpathSync, writeFileSync } from 'node:fs';
import { basename, dirname, isAbsolute, relative, resolve, sep } from 'node:path';
import { URL, pathToFileURL } from 'node:url';

// Invoke AFTER the production build, using its actual public browser directory:
// node tooling/observation-release.mjs --directory dist/studymate/browser \
//   --release-id "$PEERLY_RELEASE" --origin "$PEERLY_PUBLIC_ORIGIN" \
//   --output /tmp/peerly-observation-release.json
// Output is outside the build tree, newly created (wx), never a bundle rewrite.
// Parent owns copying/serving this artifact and approving the backend release map.
const publicJavascript = /^(?:main|polyfills|chunk)-[A-Za-z0-9_-]{1,64}\.js$/;
const maximumAssets = 4096;
const maximumEntries = 8192;

function fail(message) {
  throw new Error(message);
}

function validateIdentity(releaseId, origin) {
  if (typeof releaseId !== 'string' || !/^[0-9a-f]{40}$/.test(releaseId))
    fail('Release ID must be the actual full lowercase 40-character commit SHA');
  if (typeof origin !== 'string') fail('Public origin must be canonical HTTPS');
  try {
    const parsed = new URL(origin);
    if (parsed.origin !== origin || parsed.protocol !== 'https:')
      fail('Public origin must be canonical HTTPS without a path, query or credentials');
  } catch {
    fail('Public origin must be canonical HTTPS without a path, query or credentials');
  }
}

/** Construct exactly the readonly ReleaseAssets shape consumed by observation-privacy.ts. */
export function buildObservationRelease({ directory, releaseId, origin }) {
  validateIdentity(releaseId, origin);
  if (typeof directory !== 'string' || directory.length === 0)
    fail('Specify the actual public browser build directory');
  const root = resolve(directory);
  let handle;
  try {
    if (!lstatSync(root).isDirectory()) fail('Public build directory must be a real directory');
    handle = opendirSync(root);
  } catch {
    fail('Public build directory must be an existing real directory');
  }
  let names = [];
  let entries = 0;
  try {
    for (let entry = handle.readSync(); entry !== null; entry = handle.readSync()) {
      entries += 1;
      if (entries > maximumEntries) fail('Public build directory exceeds the bounded entry limit');
      // Do not recurse into assets/server/source directories or open JS/map contents.
      if (!entry.name.endsWith('.js')) continue;
      if (!publicJavascript.test(entry.name))
        fail('Unapproved root JavaScript basename; public frame policy must be reviewed');
      if (!entry.isFile() || entry.isSymbolicLink())
        fail('Public JavaScript assets must be regular files, never links or directories');
      names = [...names, entry.name];
      if (names.length > maximumAssets) fail('Public asset IDs exceed the supported 0..4095 range');
    }
  } finally {
    handle.closeSync();
  }
  if (names.length === 0) fail('No emitted public JavaScript assets were found');
  const assets = names.toSorted().map((basename, assetId) => Object.freeze({ basename, assetId }));
  return Object.freeze({ releaseId, origin, assets: Object.freeze(assets) });
}

export function writeObservationRelease({ directory, releaseId, origin, output }) {
  const map = buildObservationRelease({ directory, releaseId, origin });
  if (typeof output !== 'string' || output.length === 0)
    fail('Specify a new output artifact outside the public build directory');
  const target = resolve(output);
  let actualBuild;
  let actualOutput;
  try {
    actualBuild = realpathSync(resolve(directory));
    actualOutput = resolve(realpathSync(dirname(target)), basename(target));
  } catch {
    fail('Output requires an existing writable parent directory');
  }
  const fromBuild = relative(actualBuild, actualOutput);
  if (
    fromBuild === '' ||
    (!isAbsolute(fromBuild) && fromBuild !== '..' && !fromBuild.startsWith('..' + sep))
  )
    fail('Output must be outside the public build directory; bundles are read-only inputs');
  try {
    // No replacement, symlink following, or reading an existing potentially private file.
    writeFileSync(target, JSON.stringify(map, null, 2) + '\n', { flag: 'wx', mode: 0o644 });
  } catch {
    fail('Cannot create output artifact; provide a new writable output path');
  }
  return map;
}

export function observationReleaseArguments(args) {
  const names = new Map([
    ['--directory', 'directory'],
    ['--release-id', 'releaseId'],
    ['--origin', 'origin'],
    ['--output', 'output'],
  ]);
  let result = {};
  for (let index = 0; index < args.length; index += 2) {
    const name = names.get(args[index]);
    const value = args[index + 1];
    if (
      name === undefined ||
      Object.hasOwn(result, name) ||
      typeof value !== 'string' ||
      value.length === 0 ||
      value.startsWith('--')
    )
      fail('Expected exactly --directory, --release-id, --origin and --output values');
    result = { ...result, [name]: value };
  }
  if (Object.keys(result).length !== names.size)
    fail('Expected exactly --directory, --release-id, --origin and --output values');
  return result;
}

if (process.argv[1] !== undefined && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    const map = writeObservationRelease(observationReleaseArguments(process.argv.slice(2)));
    process.stdout.write(
      `Created observation release map for ${String(map.assets.length)} public JS assets.\n`,
    );
  } catch {
    // No raw filesystem error/path, URL, environment or arbitrary argument echo.
    process.stderr.write(
      'Observation release map rejected; check explicit release/origin/build/output inputs.\n',
    );
    process.exitCode = 1;
  }
}
