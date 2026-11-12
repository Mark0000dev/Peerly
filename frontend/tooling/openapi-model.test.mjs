import { URL } from 'node:url';
import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import ts from 'typescript';
import { renderApi, schemaType } from './openapi-model.mjs';

test('nested records, arrays, references, optional and nullable members stay readonly', () => {
  assert.equal(
    schemaType({
      type: 'array',
      items: {
        type: 'object',
        properties: { value: { anyOf: [{ type: 'string' }, { type: 'null' }] } },
        required: ['value'],
        additionalProperties: false,
      },
    }),
    'readonly ({readonly "value": string | null;})[]',
  );
  assert.equal(
    schemaType({ type: 'object', additionalProperties: { type: 'integer' } }),
    'Readonly<Record<string, number>>',
  );
  assert.equal(
    schemaType({ $ref: '#/components/schemas/IdentityResponse' }),
    'Api[\'schemas\']["IdentityResponse"]',
  );
  assert.equal(
    schemaType({
      type: 'object',
      properties: { value: { type: 'boolean' } },
      additionalProperties: false,
    }),
    '{readonly "value"?: boolean;}',
  );
});

test('unsupported schema changes fail loudly instead of weakening client types', () => {
  for (const schema of [
    { allOf: [] },
    { const: { mutable: 'nested' } },
    { enum: [['mutable']] },
    { $ref: 'https://outside.invalid/schema' },
    { type: 'array' },
    { type: ['string', 'null'] },
    { type: 'object', properties: { x: { type: 'string' } } },
  ])
    assert.throws(() => schemaType(schema));
});

test('actual enabled contract stays deterministic and rejects a health-only export', () => {
  const schema = JSON.parse(
    readFileSync(new URL('../contracts/openapi.json', import.meta.url), 'utf8'),
  );
  assert.equal(renderApi(schema), renderApi(schema));
  assert.throws(
    () => renderApi({ ...schema, paths: { '/api/health': schema.paths['/api/health'] } }),
    /Enabled-auth/,
  );
});

test('actual private JPEG display is immutable binary and unsupported media still fails closed', () => {
  const schema = JSON.parse(
    readFileSync(new URL('../contracts/openapi.json', import.meta.url), 'utf8'),
  );
  assert.match(renderApi(schema), /readonly "200": Readonly<Blob>/);
  for (const content of [
    { 'image/png': { schema: { type: 'string', format: 'binary' } } },
    { 'image/jpeg': { schema: { type: 'object', additionalProperties: false } } },
    { 'image/jpeg': { schema: { type: 'string', format: 'binary', unsupported: true } } },
    {
      'image/jpeg': { schema: { type: 'string', format: 'binary' } },
      'application/json': { schema: { type: 'string' } },
    },
  ]) {
    const changed = globalThis.structuredClone(schema);
    changed.paths['/api/v1/media/{upload_id}/display'].get.responses['200'].content = content;
    assert.throws(() => renderApi(changed), /Unsupported/);
  }
});

test('actual subject discriminator preserves request tags and optional response defaults', () => {
  const schema = JSON.parse(
    readFileSync(new URL('../contracts/openapi.json', import.meta.url), 'utf8'),
  );
  const definitions = schema.components.schemas;
  for (const name of ['SaveGoalRequest', 'GoalResponse']) {
    const subject = definitions[name].properties.subject;
    assert.match(schemaType(subject, definitions), /CanonicalSubject/);
    for (const discriminator of [
      null,
      { ...subject.discriminator, propertyName: '' },
      { ...subject.discriminator, extra: true },
      { ...subject.discriminator, mapping: { canonical: subject.discriminator.mapping.canonical } },
      {
        ...subject.discriminator,
        mapping: {
          canonical: subject.discriminator.mapping.canonical,
          custom: subject.discriminator.mapping.canonical,
        },
      },
      {
        ...subject.discriminator,
        mapping: {
          canonical: 'https://outside.invalid/schema',
          custom: subject.discriminator.mapping.custom,
        },
      },
      {
        ...subject.discriminator,
        mapping: {
          wrong: subject.discriminator.mapping.canonical,
          custom: subject.discriminator.mapping.custom,
        },
      },
    ])
      assert.throws(() => schemaType({ ...subject, discriminator }, definitions));
    assert.throws(() => schemaType(subject));
    assert.throws(() => schemaType({ ...subject, anyOf: subject.oneOf }, definitions));
    assert.throws(() => schemaType({ ...subject, oneOf: [{ type: 'string' }] }, definitions));
    assert.throws(() => schemaType(subject, {}));
  }
  assert.match(
    schemaType(definitions.CanonicalSubjectRequest, definitions),
    /readonly "kind": "canonical"/,
  );
  assert.match(
    schemaType(definitions.CanonicalSubjectResponse, definitions),
    /readonly "kind"\?: "canonical"/,
  );
  const changed = globalThis.structuredClone(definitions);
  delete changed.CanonicalSubjectResponse.properties.kind.default;
  assert.throws(() => schemaType(definitions.GoalResponse.properties.subject, changed));
  assert.equal(definitions.CanonicalSubjectResponse.properties.kind.default, 'canonical');
});

test('TypeScript rejects mutations of generated nested DTOs and request arrays', () => {
  const generated = readFileSync(new URL('../src/app/api.generated.ts', import.meta.url), 'utf8');
  const source =
    generated +
    `\ndeclare const identity: Api['schemas']['IdentityResponse'];\nidentity.capabilities.can_begin_onboarding = false;\ndeclare const problem: Api['schemas']['ProblemResponse'];\nproblem.errors.push({path:[],code:'bad'});\nproblem.recovery['new'] = 'value';\ndeclare const binary: Api['paths']['/api/v1/media/{upload_id}/display']['get']['responses']['200'];\nbinary.size = 0;\ndeclare const access: Api['schemas']['UploadAccessResponse'];\naccess.fields['key'] = 'changed';\ndeclare const goal: Api['schemas']['SaveGoalRequest'];\nif (goal.subject.kind === 'canonical') { const id: string = goal.subject.id; goal.subject.id = id; } else { const label: string = goal.subject.label; goal.subject.label = label; }\n`;
  const filename = '/contract-immutability.ts';
  const options = {
    strict: true,
    noEmit: true,
    skipLibCheck: true,
    target: ts.ScriptTarget.ES2022,
    ignoreDeprecations: '6.0',
  };
  const host = ts.createCompilerHost(options);
  const original = host.getSourceFile;
  host.getSourceFile = (name, ...args) =>
    name === filename
      ? ts.createSourceFile(name, source, ts.ScriptTarget.Latest, true)
      : original(name, ...args);
  const program = ts.createProgram([filename], options, host);
  const errors = ts
    .getPreEmitDiagnostics(program)
    .filter((d) => d.category === ts.DiagnosticCategory.Error);
  assert.deepEqual(
    errors.map((error) => error.code).sort(),
    [2339, 2540, 2540, 2540, 2540, 2542, 2542],
  );
});

test('actual SSE wire response remains text and rejects guessed frame or mixed media schemas', () => {
  const schema = JSON.parse(
    readFileSync(new URL('../contracts/openapi.json', import.meta.url), 'utf8'),
  );
  const content = schema.paths['/api/v1/events'].get.responses['200'].content;
  assert.deepEqual(content, { 'text/event-stream': { schema: { type: 'string' } } });
  assert.match(renderApi(schema), /readonly "200": string/);
  for (const invalid of [
    { 'text/event-stream': { schema: { type: 'object', additionalProperties: false } } },
    { 'text/event-stream': { schema: { type: 'string', format: 'binary' } } },
    { 'text/event-stream': { schema: { type: 'string', enum: ['resource.changed'] } } },
    {
      'text/event-stream': { schema: { type: 'string' } },
      'application/json': { schema: { type: 'string' } },
    },
  ]) {
    const changed = globalThis.structuredClone(schema);
    changed.paths['/api/v1/events'].get.responses['200'].content = invalid;
    assert.throws(() => renderApi(changed), /Unsupported/);
  }
});

test('actual operator original/display binary alternatives remain immutable and fail closed', () => {
  const schema = JSON.parse(
    readFileSync(new URL('../contracts/openapi.json', import.meta.url), 'utf8'),
  );
  const path =
    '/api/v1/operator/accounts/{account_id}/photo-uploads/{upload_id}/attempts/{attempt_id}/{kind}';
  const content = schema.paths[path].get.responses['200'].content;
  assert.deepEqual(Object.keys(content).toSorted(), ['application/octet-stream', 'image/jpeg']);
  assert.match(renderApi(schema), /Readonly<Blob>/);
  for (const invalid of [
    { ...content, 'application/json': { schema: { type: 'string' } } },
    { ...content, 'application/octet-stream': { schema: { type: 'string' } } },
    {
      ...content,
      'image/jpeg': { schema: { type: 'string', format: 'binary', enum: ['unsafe'] } },
    },
  ]) {
    const changed = globalThis.structuredClone(schema);
    changed.paths[path].get.responses['200'].content = invalid;
    assert.throws(() => renderApi(changed), /Unsupported/);
  }
});
