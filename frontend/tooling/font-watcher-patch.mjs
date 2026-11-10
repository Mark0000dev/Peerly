import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { URL, pathToFileURL } from 'node:url';

const entrypoints = Object.freeze([
  'index.esm.js',
  'index.cjs.js',
  'index.cjs.mjs',
  'index.cjs.default.js',
  'index.d.ts',
]);

export function verifyWatcher(version, contents, hashes, stage) {
  if (version !== '0.6.0' || !['before', 'after'].includes(stage))
    throw new Error('Unreviewed font-watcher version or patch stage');
  if (
    Object.keys(hashes).length !== entrypoints.length ||
    entrypoints.some((name) => !Object.hasOwn(hashes, name))
  )
    throw new Error('Incomplete or unreviewed font-watcher manifest');
  for (const [name, expected] of Object.entries(hashes)) {
    const source = contents[name];
    if (typeof source !== 'string') throw new Error(`Missing font-watcher entrypoint ${name}`);
    const actual = createHash('sha256').update(source).digest('hex');
    if (actual !== expected.patched && (stage !== 'before' || actual !== expected.original))
      throw new Error(`Unreviewed font-watcher source: ${name}`);
  }
}

if (process.argv[1] !== undefined && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const root = new URL('../node_modules/@taiga-ui/font-watcher/', import.meta.url);
  const metadata = JSON.parse(readFileSync(new URL('package.json', root), 'utf8'));
  const hashes = JSON.parse(
    readFileSync(new URL('./font-watcher-hashes.json', import.meta.url), 'utf8'),
  );
  const contents = Object.fromEntries(
    entrypoints.map((name) => [name, readFileSync(new URL(name, root), 'utf8')]),
  );
  verifyWatcher(metadata.version, contents, hashes, process.argv[2]);
}
