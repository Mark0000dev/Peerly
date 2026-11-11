// Intentionally limited to the OpenAPI 3.1 subset emitted by this backend.
// Unsupported validation/composition semantics fail closed instead of losing types.
function validateDiscriminator(schema, definitions) {
  const discriminator = schema.discriminator;
  const alternatives = schema.oneOf;
  if (
    typeof discriminator !== 'object' ||
    discriminator === null ||
    Array.isArray(discriminator) ||
    Object.keys(discriminator).some((key) => !['propertyName', 'mapping'].includes(key)) ||
    typeof discriminator.propertyName !== 'string' ||
    discriminator.propertyName.length === 0 ||
    typeof discriminator.mapping !== 'object' ||
    discriminator.mapping === null ||
    Array.isArray(discriminator.mapping) ||
    !Array.isArray(alternatives) ||
    alternatives.length === 0 ||
    schema.anyOf !== undefined ||
    definitions === undefined
  )
    throw new Error('Unsupported discriminator metadata');
  const references = alternatives.map((variant) => {
    if (
      typeof variant !== 'object' ||
      variant === null ||
      Object.keys(variant).some((key) => key !== '$ref') ||
      typeof variant.$ref !== 'string'
    )
      throw new Error('Unsupported discriminator branch');
    return variant.$ref;
  });
  const mapping = Object.entries(discriminator.mapping);
  if (
    mapping.length !== references.length ||
    new Set(mapping.map(([, ref]) => ref)).size !== references.length ||
    mapping.some(([, ref]) => !references.includes(ref))
  )
    throw new Error('Incomplete discriminator mapping');
  for (const [tag, ref] of mapping) {
    const name =
      typeof ref === 'string' ? /^#\/components\/schemas\/([^/]+)$/.exec(ref)?.[1] : undefined;
    const branch =
      name !== undefined && Object.hasOwn(definitions, name) ? definitions[name] : undefined;
    const field = branch?.properties?.[discriminator.propertyName];
    if (
      branch?.type !== 'object' ||
      field?.type !== 'string' ||
      field.const !== tag ||
      !(branch.required?.includes(discriminator.propertyName) === true || field.default === tag)
    )
      throw new Error('Discriminator must match a declared literal tag');
  }
  // Preserve actual required/default metadata; never inject a missing discriminator value.
}

export function schemaType(schema, definitions) {
  if (schema === true) return 'unknown';
  if (schema === false) return 'never';
  const annotations = new Set([
    'title',
    'description',
    'default',
    'examples',
    'example',
    'format',
    'minLength',
    'maxLength',
    'pattern',
    'minimum',
    'maximum',
    'exclusiveMinimum',
    'exclusiveMaximum',
    'minItems',
    'maxItems',
    'uniqueItems',
  ]);
  const supported = new Set([
    '$ref',
    'discriminator',
    'const',
    'enum',
    'anyOf',
    'oneOf',
    'type',
    'properties',
    'required',
    'additionalProperties',
    'items',
  ]);
  for (const key of Object.keys(schema)) {
    if (!annotations.has(key) && !supported.has(key))
      throw new Error(`Unsupported schema keyword: ${key}`);
  }
  if (schema.discriminator !== undefined) validateDiscriminator(schema, definitions);
  if (schema.$ref !== undefined) {
    const match = /^#\/components\/schemas\/([^/]+)$/.exec(schema.$ref);
    if (match === null) throw new Error(`Unsupported reference: ${schema.$ref}`);
    return `Api['schemas'][${JSON.stringify(match[1])}]`;
  }
  const literal = (value) => {
    if (value !== null && !['string', 'number', 'boolean'].includes(typeof value))
      throw new Error('Non-scalar literal unsupported');
    return JSON.stringify(value);
  };
  if ('const' in schema) return literal(schema.const);
  if (schema.enum !== undefined) return schema.enum.map(literal).join(' | ');
  const alternatives = schema.anyOf ?? schema.oneOf;
  if (alternatives !== undefined)
    return alternatives.map((value) => schemaType(value, definitions)).join(' | ');
  if (Object.keys(schema).length === 0) return 'unknown';
  switch (schema.type) {
    case 'string':
      return 'string';
    case 'integer':
    case 'number':
      return 'number';
    case 'boolean':
      return 'boolean';
    case 'null':
      return 'null';
    case 'array':
      if (schema.items === undefined) throw new Error('Array without item schema');
      return `readonly (${schemaType(schema.items, definitions)})[]`;
    case 'object': {
      const properties = Object.entries(schema.properties ?? {})
        .map(
          ([name, value]) =>
            `readonly ${JSON.stringify(name)}${schema.required?.includes(name) === true ? '' : '?'}: ${schemaType(value, definitions)};`,
        )
        .join('\n');
      const additional = schema.additionalProperties;
      if (additional !== undefined && additional !== false && properties !== '')
        throw new Error('Mixed fixed and additional properties require explicit support');
      if (additional === true || additional === undefined) {
        if (properties !== '')
          throw new Error('Open object with fixed properties requires explicit support');
        return 'Readonly<Record<string, unknown>>';
      }
      if (additional !== false)
        return `Readonly<Record<string, ${schemaType(additional, definitions)}>>`;
      return properties === '' ? 'Readonly<Record<string, never>>' : `{${properties}}`;
    }
    default:
      throw new Error(`Unsupported schema type: ${schema.type}`);
  }
}

function contentType(content, definitions) {
  if (content === undefined) return 'undefined';
  const media = Object.keys(content);
  if (
    media.length > 0 &&
    media.every((type) => ['image/jpeg', 'application/octet-stream'].includes(type))
  ) {
    for (const type of media) {
      const binary = content[type].schema;
      if (
        binary?.type !== 'string' ||
        binary.format !== 'binary' ||
        Object.keys(binary).some((key) => !['type', 'format', 'title', 'description'].includes(key))
      )
        throw new Error('Unsupported binary response schema');
    }
    return 'Readonly<Blob>';
  }
  if (Object.keys(content).length === 1 && 'text/event-stream' in content) {
    const stream = content['text/event-stream'].schema;
    if (
      stream?.type !== 'string' ||
      Object.keys(stream).some((key) => !['type', 'title', 'description'].includes(key))
    )
      throw new Error('Unsupported event-stream response schema');
    // This describes the wire text, not a fabricated JSON frame DTO or transport client.
    return 'string';
  }
  const entry = content['application/json'];
  if (entry === undefined || Object.keys(content).length !== 1)
    throw new Error('Unsupported response content');
  return schemaType(entry.schema, definitions);
}

export function renderApi(schema) {
  if (schema.openapi !== '3.1.0') throw new Error('Expected OpenAPI 3.1.0');
  for (const path of [
    '/api/health',
    '/api/ready',
    '/api/v1/me',
    '/api/v1/auth/logout',
    '/api/v1/auth/email-challenges',
  ]) {
    if (!(path in schema.paths)) throw new Error(`Enabled-auth contract missing ${path}`);
  }
  const definitions = schema.components.schemas;
  const models = Object.entries(definitions)
    .map(([name, value]) => `readonly ${JSON.stringify(name)}: ${schemaType(value, definitions)};`)
    .join('\n');
  const paths = Object.entries(schema.paths)
    .map(([path, methods]) => {
      const operations = Object.entries(methods)
        .map(([method, operation]) => {
          if (!['get', 'post', 'put', 'patch', 'delete', 'head', 'options'].includes(method))
            throw new Error(`Unsupported path item: ${method}`);
          const parameters = (operation.parameters ?? [])
            .map((parameter) => {
              if (parameter.$ref !== undefined) throw new Error('Referenced parameter unsupported');
              return `readonly ${JSON.stringify(`${parameter.in}:${parameter.name}`)}${parameter.required === true ? '' : '?'}: ${schemaType(parameter.schema, definitions)};`;
            })
            .join('\n');
          const responses = Object.entries(operation.responses)
            .map(
              ([status, response]) =>
                `readonly ${JSON.stringify(status)}: ${contentType(response.content, definitions)};`,
            )
            .join('\n');
          return `readonly ${JSON.stringify(method)}: {readonly parameters: ${parameters === '' ? 'Readonly<Record<string, never>>' : `{${parameters}}`}; readonly body: ${contentType(operation.requestBody?.content, definitions)}; readonly responses: {${responses}};};`;
        })
        .join('\n');
      return `readonly ${JSON.stringify(path)}: {${operations}};`;
    })
    .join('\n');
  return `// Generated from enabled-auth FastAPI OpenAPI. Run npm run contracts:generate.\n// Do not edit. Constraints such as string lengths remain server-validated.\nexport interface Api {readonly schemas: {${models}}; readonly paths: {${paths}};}\n`;
}
