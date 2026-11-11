import assert from 'node:assert/strict';
import { Buffer } from 'node:buffer';
import test from 'node:test';
import {
  mkdtempSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { URL, fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import {
  buildObservationRelease,
  observationReleaseArguments,
  writeObservationRelease,
} from './observation-release.mjs';

const releaseId = 'a'.repeat(40);
const origin = 'https://peerly.example.test';
const command = fileURLToPath(new URL('./observation-release.mjs', import.meta.url));
function fixture(
  context,
  names = ['main-Z9.js', 'chunk--7w4dfX0.js', 'polyfills-B2.js', 'chunk-A_1.js'],
) {
  const root = mkdtempSync(join(tmpdir(), 'peerly-observation-release-'));
  context.after(() => {
    rmSync(root, { recursive: true, force: true });
  });
  const directory = join(root, 'browser');
  mkdirSync(directory);
  for (const name of names) writeFileSync(join(directory, name), 'export {};\n');
  return { root, directory, releaseId, origin };
}

// This is the actual production reader evaluated without importing Angular or creating
// another handwritten validation policy. Only type syntax is removed for Node tooling.
async function browserReader() {
  const source = readFileSync(
    new URL('../src/app/observability/observation-privacy.ts', import.meta.url),
    'utf8',
  );
  const start = source.indexOf('export function validatedRelease(');
  const end = source.indexOf('// Stack text', start);
  assert.ok(start >= 0 && end > start, 'Actual public release validator must remain available');
  const ts = (await import('typescript')).default;
  const javascript = ts.transpileModule(source.slice(start, end), {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 },
  }).outputText;
  const module = await import(
    'data:text/javascript;base64,' + Buffer.from(javascript).toString('base64')
  );
  return module.validatedRelease;
}

test('real directory enumeration produces sorted deterministic numeric IDs accepted by the actual browser policy', async (context) => {
  const setup = fixture(context);
  const map = buildObservationRelease(setup);
  assert.deepEqual(map, {
    releaseId,
    origin,
    assets: [
      { basename: 'chunk--7w4dfX0.js', assetId: 0 },
      { basename: 'chunk-A_1.js', assetId: 1 },
      { basename: 'main-Z9.js', assetId: 2 },
      { basename: 'polyfills-B2.js', assetId: 3 },
    ],
  });
  assert.deepEqual((await browserReader())(map), map);
  assert.ok(
    Object.isFrozen(map) && Object.isFrozen(map.assets) && map.assets.every(Object.isFrozen),
  );
  const alternate = fixture(context, [
    'chunk-A_1.js',
    'polyfills-B2.js',
    'main-Z9.js',
    'chunk--7w4dfX0.js',
  ]);
  assert.equal(JSON.stringify(buildObservationRelease(alternate)), JSON.stringify(map));
});

test('artifact exposes only ReleaseAssets fields; maps, nested files and contents remain private and untouched', (context) => {
  const setup = fixture(context);
  writeFileSync(join(setup.directory, 'main-Z9.js.map'), 'PRIVATE_SOURCEMAP_EMAIL');
  mkdirSync(join(setup.directory, 'assets'));
  writeFileSync(join(setup.directory, 'assets', 'main-PRIVATE.js'), 'PRIVATE_NESTED_SOURCE');
  const before = readdirSync(setup.directory).map((name) => [
    name,
    name.endsWith('.js') ? readFileSync(join(setup.directory, name), 'utf8') : null,
  ]);
  const output = join(setup.root, 'observation-release.json');
  const map = writeObservationRelease({ ...setup, output });
  const text = readFileSync(output, 'utf8');
  assert.equal(text, JSON.stringify(map, null, 2) + '\n');
  assert.doesNotMatch(text, /PRIVATE|\.map|browser|\/tmp|\/home|assets\//);
  assert.deepEqual(
    readdirSync(setup.directory).map((name) => [
      name,
      name.endsWith('.js') ? readFileSync(join(setup.directory, name), 'utf8') : null,
    ]),
    before,
  );
  assert.deepEqual(Object.keys(JSON.parse(text)), ['releaseId', 'origin', 'assets']);
});

test('invalid release identity/origin fails closed without an artifact', (context) => {
  const setup = fixture(context);
  for (const value of ['', 'short', 'A'.repeat(40), 'a'.repeat(41)])
    assert.throws(() => buildObservationRelease({ ...setup, releaseId: value }));
  for (const value of [
    'http://peerly.example.test',
    origin + '/',
    origin + '/private',
    origin + '?email=private',
    origin + '#private',
    'https://private@peerly.example.test',
    'https://PEERLY.example.test',
    'not a URL',
  ])
    assert.throws(() => buildObservationRelease({ ...setup, origin: value }));
});

test('symlinks, unexpected root scripts and empty catalogs never silently manufacture a release map', (context) => {
  const empty = fixture(context, []);
  assert.throws(() => buildObservationRelease(empty), /No emitted/);
  const invalid = fixture(context, ['unapproved-private.js']);
  assert.throws(() => buildObservationRelease(invalid), /Unapproved/);
  const linked = fixture(context, []);
  const privateSource = join(linked.root, 'private.txt');
  writeFileSync(privateSource, 'PRIVATE');
  symlinkSync(privateSource, join(linked.directory, 'main-LINK.js'));
  assert.throws(() => buildObservationRelease(linked), /regular files/);
  const rootLink = join(linked.root, 'browser-link');
  symlinkSync(empty.directory, rootLink);
  assert.throws(
    () => buildObservationRelease({ ...linked, directory: rootLink }),
    /real directory/,
  );
});

test('asset count cannot exceed backend and browser numeric ID limits', (context) => {
  const setup = fixture(
    context,
    Array.from({ length: 4096 }, (_, index) => `chunk-${String(index).padStart(4, '0')}.js`),
  );
  const accepted = buildObservationRelease(setup);
  assert.equal(accepted.assets.length, 4096);
  assert.equal(accepted.assets.at(-1).assetId, 4095);
  writeFileSync(join(setup.directory, 'main-OVERFLOW.js'), 'export {};');
  assert.throws(() => buildObservationRelease(setup), /0\.\.4095/);
});

test('writing cannot modify public build outputs or replace existing files/symlinks', (context) => {
  const setup = fixture(context);
  assert.throws(
    () =>
      writeObservationRelease({
        ...setup,
        output: join(setup.directory, 'observation-release.json'),
      }),
    /outside/,
  );
  assert.throws(
    () => writeObservationRelease({ ...setup, output: join(setup.directory, 'main-Z9.js') }),
    /outside/,
  );
  const buildAlias = join(setup.root, 'build-alias');
  symlinkSync(setup.directory, buildAlias);
  assert.throws(
    () => writeObservationRelease({ ...setup, output: join(buildAlias, 'release.json') }),
    /outside/,
  );
  const existing = join(setup.root, 'existing.json');
  writeFileSync(existing, 'PRIVATE_EXISTING');
  assert.throws(() => writeObservationRelease({ ...setup, output: existing }), /new writable/);
  assert.equal(readFileSync(existing, 'utf8'), 'PRIVATE_EXISTING');
  const linked = join(setup.root, 'linked.json');
  symlinkSync(existing, linked);
  assert.throws(() => writeObservationRelease({ ...setup, output: linked }), /new writable/);
  assert.equal(readFileSync(existing, 'utf8'), 'PRIVATE_EXISTING');
});

test('CLI accepts exact explicit inputs, emits the artifact and never echoes rejected private arguments', (context) => {
  const setup = fixture(context);
  const output = join(setup.root, 'release.json');
  const args = [
    '--directory',
    setup.directory,
    '--release-id',
    releaseId,
    '--origin',
    origin,
    '--output',
    output,
  ];
  assert.deepEqual(observationReleaseArguments(args), {
    directory: setup.directory,
    releaseId,
    origin,
    output,
  });
  const result = spawnSync(process.execPath, [command, ...args], {
    encoding: 'utf8',
    timeout: 10000,
  });
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(JSON.parse(readFileSync(output, 'utf8')), buildObservationRelease(setup));
  const rejected = spawnSync(
    process.execPath,
    [command, ...args, '--private-secret', 'PRIVATE_VALUE'],
    { encoding: 'utf8', timeout: 10000 },
  );
  assert.equal(rejected.status, 1);
  assert.doesNotMatch(
    rejected.stderr + rejected.stdout,
    /PRIVATE_VALUE|private-secret|\/tmp|\/home/,
  );
  assert.throws(() => observationReleaseArguments([...args, '--origin', origin]));
  assert.throws(() => observationReleaseArguments(args.slice(0, -1)));
});
