import { describe, expect, it } from 'vitest';
import { callbackNotice } from './callback';

describe('untrusted callback presentation metadata', () => {
  for (const code of [
    'login_invalid',
    'login_cancelled',
    'login_provider_unavailable',
    'login_rate_limited',
    'account_unavailable',
    'request_context_invalid',
  ]) {
    it(`allows only documented copy for ${code}`, () => {
      expect(callbackNotice(code, '00000000-0000-0000-0000-000000000001')).toMatchObject({
        reference: '00000000-0000-0000-0000-000000000001',
        cancelled: code === 'login_cancelled',
      });
    });
  }
  for (const code of [
    null,
    'access_denied',
    'constructor',
    '__proto__',
    '<script>private()</script>',
  ]) {
    it(`ignores unknown provider/URL text ${String(code)}`, () => {
      expect(callbackNotice(code, 'private@mail.apu.edu.my')).toBeNull();
    });
  }
  for (const reference of [null, 'private@mail.apu.edu.my', '<script>private()</script>']) {
    it(`does not echo an arbitrary reference ${String(reference)}`, () => {
      expect(callbackNotice('login_invalid', reference)?.reference).toBeNull();
    });
  }
});
