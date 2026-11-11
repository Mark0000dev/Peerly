import type { Page } from '@playwright/test';
import type { Api } from '../src/app/api.generated';
import { isControlledPeople } from './controlled-people';
import { expect } from './visual';

// Loopback driver only: fresh real profile/photo/registration/source/request use cases.
// Credentials stay in the HTTP-only fixture session; returned values are selectors.
export async function prepareComposerFixture(
  page: Readonly<Page>,
  mode: Api['schemas']['DiscoveryMode'],
  scenario:
    'fresh' | 'outgoing' | 'incoming' | 'connected' | 'source-change' | 'lost-reply' | 'draft',
  project: string,
): Promise<{
  readonly viewerId: string;
  readonly personId: string;
  readonly subjectId: string;
  readonly subjectLabel: string;
}> {
  if (!/^(chromium-mobile|webkit-mobile|chromium-desktop)$/.test(project))
    throw new Error('Invalid controlled composer project');
  const response = await page.request.post('http://127.0.0.1:8768/__fixture/composer', {
    data: { namespace: `composer/${mode}/${scenario}/${project}` },
  });
  expect(response.status()).toBe(201);
  const value: unknown = await response.json();
  if (
    !isControlledPeople(value) ||
    !('subject_id' in value) ||
    typeof value.subject_id !== 'string' ||
    !/^[a-f0-9-]{36}$/.test(value.subject_id) ||
    !('subject_label' in value) ||
    typeof value.subject_label !== 'string' ||
    value.subject_label.length === 0 ||
    value.subject_label.length > 80
  )
    throw new Error('Invalid controlled composer cohort');
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
