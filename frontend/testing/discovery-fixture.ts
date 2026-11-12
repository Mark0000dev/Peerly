import { isControlledPeople } from './controlled-people';
import type { ControlledPeople } from './controlled-people';
import type { Page } from '@playwright/test';
import { expect } from './visual';

interface ControlledDiscovery extends ControlledPeople {
  readonly subject_id: string;
  readonly subject_label: string;
}
function isControlledDiscovery(value: unknown): value is ControlledDiscovery {
  if (typeof value !== 'object' || value === null) return false;
  return (
    isControlledPeople(value) &&
    'subject_id' in value &&
    typeof value.subject_id === 'string' &&
    /^[a-f0-9-]{36}$/.test(value.subject_id) &&
    'subject_label' in value &&
    typeof value.subject_label === 'string' &&
    value.subject_label.length > 0 &&
    value.subject_label.length <= 80
  );
}

// Test driver only. Membership/session facts are controlled; actual save/worker/registration
// use cases establish readiness, canonical help and explicit shared-learning goals in all modes.
// The browser receives a live synthetic session; credentials never enter production stores/UI.
export async function prepareDiscoveryFixture(
  page: Readonly<Page>,
  namespace: string,
): Promise<{
  readonly viewerId: string;
  readonly personId: string;
  readonly subjectId: string;
  readonly subjectLabel: string;
}> {
  if (!/^(modes|pass|undo)\/(chromium-mobile|webkit-mobile|chromium-desktop)$/.test(namespace))
    throw new Error('Invalid controlled discovery namespace');
  const response = await page.request.post('http://127.0.0.1:8768/__fixture/discovery', {
    data: { namespace },
  });
  expect(response.status()).toBe(201);
  const value: unknown = await response.json();
  if (!isControlledDiscovery(value)) throw new Error('Invalid controlled discovery seed');
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
    subjectId: value.subject_id,
    subjectLabel: value.subject_label,
  };
}
