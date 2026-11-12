import assert from 'node:assert/strict';
import { existsSync, mkdtempSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import { URL, fileURLToPath } from 'node:url';

function emittedSiblings(directory) {
  const extensions = [
    ['.js', '.ts'],
    ['.jsx', '.tsx'],
    ['.mjs', '.mts'],
    ['.cjs', '.cts'],
  ];
  return readdirSync(directory, { recursive: true, withFileTypes: true })
    .filter((entry) => entry.isFile())
    .flatMap((entry) => {
      const file = join(entry.parentPath, entry.name);
      return extensions.some(([output, source]) => {
        const suffix = entry.name.endsWith(`${output}.map`) ? `${output}.map` : output;
        return entry.name.endsWith(suffix) && existsSync(file.slice(0, -suffix.length) + source);
      })
        ? [file]
        : [];
    })
    .toSorted();
}

test('application source contains no compiler-emitted JavaScript siblings', () => {
  assert.deepEqual(
    emittedSiblings(fileURLToPath(new URL('../src/', import.meta.url))),
    [],
    'Use ngc --noEmit for template checks; compiler output belongs outside src',
  );
});

test('emission guard detects output and maps while preserving unrelated JavaScript assets', () => {
  const directory = mkdtempSync(join(tmpdir(), 'peerly-emission-guard-'));
  try {
    for (const name of ['component.ts', 'component.js', 'component.js.map', 'asset.js'])
      writeFileSync(join(directory, name), '');
    assert.deepEqual(emittedSiblings(directory), [
      join(directory, 'component.js'),
      join(directory, 'component.js.map'),
    ]);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});
