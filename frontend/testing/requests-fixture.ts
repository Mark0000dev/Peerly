import type { Page } from '@playwright/test';
import { expect } from './visual';
import { isControlledPeople } from './controlled-people';
import type { ControlledPeople } from './controlled-people';

interface ControlledRequests extends ControlledPeople {
  readonly request_id: string;
  readonly text: string;
}
function isControlledRequests(value: unknown): value is ControlledRequests {
  return (
    isControlledPeople(value) &&
    'request_id' in value &&
    typeof value.request_id === 'string' &&
    /^[a-f0-9-]{36}$/.test(value.request_id) &&
    'text' in value &&
    typeof value.text === 'string' &&
    value.text.length > 0 &&
    value.text.length <= 240
  );
}

// Driver-only identities and real profile/photo/registration/preview/send use cases.
// Requests are participant-scoped; fresh actors isolate every call without catalog noise.
export async function prepareRequestsFixture(
  page: Readonly<Page>,
  direction: 'received' | 'sent',
): Promise<{
  readonly viewerId: string;
  readonly personId: string;
  readonly requestId: string;
  readonly text: string;
}> {
  const response = await page.request.post('http://127.0.0.1:8768/__fixture/requests', {
    data: { direction },
  });
  expect(response.status()).toBe(201);
  const value: unknown = await response.json();
  if (!isControlledRequests(value)) throw new Error('Invalid controlled Requests seed');
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
  return {
    viewerId: value.viewer_id,
    personId: value.peer_id,
    requestId: value.request_id,
    text: value.text,
  };
}
