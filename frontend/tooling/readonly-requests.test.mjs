import assert from 'node:assert/strict';
import test from 'node:test';
import { applicationOrigin, isBusinessWrite } from '../testing/readonly-requests.mts';

const origin = 'https://peerly.example.test';
const endpoint = '/api/v1/telemetry/events';

test('expected origin comes from the application configuration, including canonical ports', () => {
  assert.equal(applicationOrigin(`${origin}/chats?conversation=synthetic#context`), origin);
  assert.equal(applicationOrigin('https://PEERLY.example.test:443/'), origin);
  assert.equal(applicationOrigin('http://127.0.0.1:4345/'), 'http://127.0.0.1:4345');
});

for (const baseURL of [
  undefined,
  '',
  'not a URL',
  'file:///tmp/test',
  'ftp://peerly.example.test',
  'https://synthetic-user:synthetic-password@peerly.example.test',
]) {
  test(`invalid application configuration fails closed: ${String(baseURL)}`, () => {
    assert.throws(() => applicationOrigin(baseURL), /application base URL/);
  });
}

test('only the exact mandatory observation POST on the configured origin is exempt', () => {
  assert.equal(isBusinessWrite('POST', `${origin}${endpoint}`, origin), false);
  assert.equal(
    isBusinessWrite('POST', `https://PEERLY.example.test:443${endpoint}`, origin),
    false,
  );
  assert.equal(isBusinessWrite('GET', `${origin}/api/v1/conversations`, origin), false);
});

for (const method of ['PUT', 'PATCH', 'DELETE', 'OPTIONS', 'HEAD', 'post', '']) {
  test(`a different non-GET method remains unexpected: ${method}`, () => {
    assert.equal(isBusinessWrite(method, `${origin}${endpoint}`, origin), true);
  });
}

for (const requestURL of [
  `https://attacker.example.test${endpoint}`,
  `https://peerly.example.test.attacker.test${endpoint}`,
  `http://peerly.example.test${endpoint}`,
  `https://peerly.example.test:444${endpoint}`,
  `https://synthetic-user@peerly.example.test${endpoint}`,
  `${origin}${endpoint}/`,
  `${origin}${endpoint}-extra`,
  `${origin}${endpoint}/extra`,
  `${origin}/api/v1/telemetry/%65vents`,
  `${origin}${endpoint}?unexpected=1`,
  `${origin}${endpoint}#unexpected`,
  'not a URL',
]) {
  test(`a foreign, malformed or nonexact observation URL is not exempt: ${requestURL}`, () => {
    assert.equal(isBusinessWrite('POST', requestURL, origin), true);
  });
}

test('all message, ACK, visit and other business commands remain guarded', () => {
  for (const [method, path] of [
    ['POST', '/api/v1/conversations/synthetic/messages'],
    ['PUT', '/api/v1/conversations/synthetic/read-position'],
    ['POST', '/api/v1/conversations/synthetic/study-prompt-visits'],
    ['POST', '/api/v1/requests'],
    ['DELETE', '/api/v1/me'],
  ])
    assert.equal(isBusinessWrite(method, `${origin}${path}`, origin), true);
});
