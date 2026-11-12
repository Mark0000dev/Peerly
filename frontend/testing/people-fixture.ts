import { isControlledPeople } from './controlled-people';
import type { Page } from '@playwright/test';
import { expect } from './visual';

// Test driver only. Membership/session facts are controlled; readiness comes from actual profile,
// goal, SQL photo worker/codec and issued registration use cases. OAuth/OTP UI has its own real suite.
// The browser receives a live synthetic session; credentials never enter production stores/UI.
export async function preparePersonFixture(page: Readonly<Page>): Promise<{
  readonly viewerId: string;
  readonly personId: string;
}> {
  const response = await page.request.post('http://127.0.0.1:8768/__fixture/people');
  expect(response.status()).toBe(201);
  const value: unknown = await response.json();
  if (!isControlledPeople(value)) throw new Error('Invalid controlled person seed');
  await page.context().addCookies([
    {
      name: value.cookie_name,
      value: value.viewer_session,
      url: value.origin,
      httpOnly: true,
      secure: true,
      sameSite: 'Lax',
    },
  ]);
  return { viewerId: value.viewer_id, personId: value.peer_id };
}
