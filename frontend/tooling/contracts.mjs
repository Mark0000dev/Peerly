import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
import { URL, fileURLToPath } from 'node:url';
import { format, resolveConfig } from 'prettier';
import { renderApi } from './openapi-model.mjs';

const root = new URL('../', import.meta.url);
const output = new URL('src/app/api.generated.ts', root);
const snapshot = new URL('contracts/openapi.json', root);
const source = execFileSync(
  fileURLToPath(new URL('../backend/.venv/bin/python', root)),
  ['-m', 'studymate.export_openapi'],
  {
    cwd: fileURLToPath(new URL('../backend/', root)),
    encoding: 'utf8',
    maxBuffer: 10 * 1024 * 1024,
  },
);
const schema = JSON.parse(source);
const config = await resolveConfig(fileURLToPath(new URL('.prettierrc', root)));
const json = await format(JSON.stringify(schema), { ...config, parser: 'json' });
const types = await format(renderApi(schema), { ...config, parser: 'typescript' });
if (process.argv.includes('--write')) {
  writeFileSync(snapshot, json);
  writeFileSync(output, types);
} else {
  if (readFileSync(snapshot, 'utf8') !== json || readFileSync(output, 'utf8') !== types) {
    throw new Error('Backend OpenAPI drift: review and run npm run contracts:generate');
  }
}
