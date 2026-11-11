import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { URL } from 'node:url';

test('Knip font asset exceptions require real pinned local WOFF2 consumers', () => {
  const root = new URL('../', import.meta.url);
  const config = JSON.parse(readFileSync(new URL('knip.json', root), 'utf8'));
  const manifest = JSON.parse(readFileSync(new URL('package.json', root), 'utf8'));
  const styles = readFileSync(new URL('src/styles.less', root), 'utf8');
  const references = [...styles.matchAll(/url\(['"](@fontsource\/[^'"]+\.woff2)['"]\)/g)];
  for (const dependency of config.ignoreDependencies.filter((name) =>
    name.startsWith('@fontsource/'),
  )) {
    assert.match(manifest.dependencies[dependency], /^\d+\.\d+\.\d+$/);
    const assets = references.filter((match) => match[1].startsWith(`${dependency}/files/`));
    assert.ok(assets.length > 0, `${dependency} must have an actual stylesheet consumer`);
    for (const asset of assets) {
      const bytes = readFileSync(new URL(`node_modules/${asset[1]}`, root));
      assert.equal(bytes.subarray(0, 4).toString('ascii'), 'wOF2');
    }
  }
});
