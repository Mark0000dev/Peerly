import type { Page, TestInfo } from '@playwright/test';
import { test, expect } from '../../../../../testing/visual';
import { verifyFixtureStudent } from '../../../../../testing/verified-student';

function submittedActionEvent(
  submitted: unknown,
  actionId: string | undefined,
): Readonly<{ readonly actionEventId: string; readonly eventIds: readonly string[] }> {
  if (
    typeof submitted !== 'object' ||
    submitted === null ||
    !('events' in submitted) ||
    !Array.isArray(submitted.events)
  )
    throw new Error('Missing actual observation batch');
  const submittedEvents: readonly unknown[] = submitted.events;
  const action = submittedEvents.find(
    (event) =>
      typeof event === 'object' &&
      event !== null &&
      'kind' in event &&
      event.kind === 'action.observed' &&
      'action_id' in event &&
      event.action_id === actionId,
  );
  if (
    typeof action !== 'object' ||
    action === null ||
    !('event_id' in action) ||
    typeof action.event_id !== 'string'
  )
    throw new Error('Missing actual command observation correlation');
  return {
    actionEventId: action.event_id,
    eventIds: submittedEvents.map((event) => {
      if (
        typeof event !== 'object' ||
        event === null ||
        !('event_id' in event) ||
        typeof event.event_id !== 'string'
      )
        throw new Error('Invalid submitted event identity');
      return event.event_id;
    }),
  };
}

test('real canonical alias and custom choices save and reload immutable goal revisions in PostgreSQL', async ({
  page,
  checkpoint,
}: {
  readonly page: Page;
  readonly checkpoint: (name: string) => Promise<void>;
}, info: Readonly<TestInfo>) => {
  // This compound case includes two real sign-in page boots, native membership
  // verification, two durable goal revisions/reloads and the real6.1s intake
  // spacing. The owned remote WebKit is CPU-capped; keep individual assertions
  // unchanged while bounding this complete scenario, not every browser test.
  test.setTimeout(90_000);
  await verifyFixtureStudent(page, info.project.name, 'goal');
  await page.getByRole('button', { name: 'Your study goal', exact: true }).click();
  await expect(page.getByLabel('Knowledge area', { exact: true })).toHaveValue('');
  await checkpoint('real-goal-empty.png');
  await page.getByLabel('Knowledge area', { exact: true }).fill('Databases');
  await expect(page.getByRole('option', { name: /SQL/ })).toBeVisible();
  await checkpoint('real-goal-catalogue-alias.png');
  await page.getByRole('option', { name: /SQL/ }).click();
  await page.getByLabel('Task or topic · optional', { exact: true }).fill('JOINs');
  await page.getByRole('checkbox', { name: 'Open to studying together', exact: true }).check();
  const saved = page.waitForResponse(
    (response) =>
      response.url().endsWith('/api/v1/me/goal') && response.request().method() === 'PUT',
  );
  const observation = page.waitForResponse((candidate) => {
    if (!candidate.url().endsWith('/api/v1/telemetry/events')) return false;
    const batch: unknown = candidate.request().postDataJSON();
    if (
      typeof batch !== 'object' ||
      batch === null ||
      !('events' in batch) ||
      !Array.isArray(batch.events)
    )
      return false;
    const events: readonly unknown[] = batch.events;
    return events.some(
      (event) =>
        typeof event === 'object' &&
        event !== null &&
        'kind' in event &&
        event.kind === 'action.observed' &&
        'action' in event &&
        event.action === 'submit',
    );
  });
  await page.getByRole('button', { name: 'Save goal', exact: true }).click();
  const response = await saved;
  expect(response.status()).toBe(200);
  const body: unknown = await response.json();
  expect(body).toMatchObject({
    version: 1,
    subject: { kind: 'canonical', label: 'SQL' },
    topic: 'JOINs',
    shared_learning: true,
  });
  await expect(
    page.getByText('Goal saved. New requests will use this goal.', { exact: true }),
  ).toBeVisible();
  const actionId = response.request().headers()['x-action-id'];
  expect(actionId).toMatch(/^[a-f0-9-]{36}$/);
  const intake = await observation;
  expect(intake.status()).toBe(200);
  const submitted: unknown = intake.request().postDataJSON();
  const correlation = submittedActionEvent(submitted, actionId);
  const accepted: unknown = await intake.json();
  expect(correlation.eventIds).toContain(correlation.actionEventId);
  expect(accepted).toEqual({
    accepted: correlation.eventIds,
    duplicates: [],
    received_at: expect.any(String),
    schema_version: 1,
  });
  expect(JSON.stringify(submitted)).not.toContain('JOINs');
  expect(JSON.stringify(submitted)).not.toContain('x-csrf-token');
  await checkpoint('real-goal-saved.png');
  await page.reload();
  await page.getByRole('button', { name: 'Your study goal', exact: true }).click();
  await expect(page.getByLabel('Knowledge area', { exact: true })).toHaveValue('SQL');
  await expect(page.getByLabel('Task or topic · optional', { exact: true })).toHaveValue('JOINs');
  await expect(
    page.getByRole('checkbox', { name: 'Open to studying together', exact: true }),
  ).toBeChecked();
  await checkpoint('real-goal-reloaded.png');
  await page.getByLabel('Knowledge area', { exact: true }).fill('Distributed systems');
  await expect(page.getByText('No areas found.', { exact: true })).toBeVisible();
  await page.getByRole('option', { name: 'Use this as another area', exact: true }).click();
  const customSave = page.waitForResponse(
    (response) =>
      response.url().endsWith('/api/v1/me/goal') && response.request().method() === 'PUT',
  );
  await page.getByRole('button', { name: 'Save goal', exact: true }).click();
  const customResponse = await customSave;
  expect(customResponse.status()).toBe(200);
  const customBody: unknown = await customResponse.json();
  expect(customBody).toMatchObject({
    version: 2,
    subject: { kind: 'custom', label: 'Distributed systems' },
    topic: 'JOINs',
    shared_learning: true,
  });
  await expect(
    page.getByText('Goal saved. New requests will use this goal.', { exact: true }),
  ).toBeVisible();
  await checkpoint('real-goal-custom-saved.png');
  await page.reload();
  await page.getByRole('button', { name: 'Your study goal', exact: true }).click();
  await expect(page.getByLabel('Knowledge area', { exact: true })).toHaveValue(
    'Distributed systems',
  );
  await expect(page.getByLabel('Task or topic · optional', { exact: true })).toHaveValue('JOINs');
  await checkpoint('real-goal-custom-reloaded.png');
});
