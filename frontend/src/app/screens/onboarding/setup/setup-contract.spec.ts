import { describe, expect, it } from 'vitest';
import {
  isRegistrationContext,
  isRegistrationReceipt,
  isSetupStatus,
  isVisibility,
} from './setup-contract';
import { complete, context, ready, receipt, visibility } from './setup.fixtures';

describe('actual setup response boundary', () => {
  for (const { name, valid, guard } of [
    { name: 'readiness', valid: complete, guard: isSetupStatus },
    { name: 'visibility', valid: visibility, guard: isVisibility },
    { name: 'context', valid: context, guard: isRegistrationContext },
    { name: 'receipt', valid: receipt, guard: isRegistrationReceipt },
  ] as const) {
    it(`accepts actual ${name} and rejects malformed root`, () => {
      expect(guard(valid)).toBe(true);
      for (const invalid of [null, [], 'private', false, 0, undefined, {}])
        expect(guard(invalid)).toBe(false);
    });
    for (const key of Object.keys(valid)) {
      it(`rejects missing ${name}.${key}`, () => {
        const missing = Object.fromEntries(
          Object.entries(valid).filter(
            ([property]: readonly [string, unknown]) => property !== key,
          ),
        );
        expect(guard(missing)).toBe(false);
      });
    }
  }
  it('validates every declared capability instead of accepting a partial or truthy projection', () => {
    for (const key of Object.keys(ready.capabilities)) {
      expect(
        isSetupStatus({ ...ready, capabilities: { ...ready.capabilities, [key]: 'true' } }),
      ).toBe(false);
    }
    expect(isSetupStatus({ ...ready, capabilities: [] })).toBe(false);
  });
  it('accepts only declared setup and restore requirements', () => {
    expect(
      isSetupStatus({
        ...ready,
        setup_requirements: ['display_name', 'photo', 'study_goal', 'help_subjects'],
        restore_requirements: ['photo', 'study_context'],
      }),
    ).toBe(true);
    expect(isSetupStatus({ ...ready, setup_requirements: ['ai'] })).toBe(false);
    expect(isSetupStatus({ ...ready, restore_requirements: ['legal_acceptance'] })).toBe(false);
  });
  it('validates nullable visibility and freshness projection before any action', () => {
    expect(isSetupStatus(ready)).toBe(true);
    for (const exposure of [
      { paused: true, can_confirm: true },
      { paused: true, can_confirm: 1, requirements: [] },
      { paused: true, can_confirm: true, requirements: ['other'] },
      { paused: 1, can_confirm: true, requirements: [] },
    ]) {
      expect(isSetupStatus({ ...ready, discovery_exposure: exposure })).toBe(false);
    }
    expect(isSetupStatus({ ...ready, visibility: { ...visibility, version: 0 } })).toBe(false);
  });
  it('rejects unsafe versions and malformed dates', () => {
    for (const version of [0, -1, 1.2, Number.MAX_SAFE_INTEGER + 1, '1'])
      expect(isVisibility({ ...visibility, version })).toBe(false);
    expect(isVisibility({ ...visibility, hidden_at: '2026-11-07T12:00:00Z' })).toBe(true);
    for (const key of ['hidden_at', 'changed_at', 'completed_at'])
      expect(isVisibility({ ...visibility, [key]: 'invalid' })).toBe(false);
    expect(isRegistrationContext({ ...context, expires_at: 'invalid' })).toBe(false);
    expect(isRegistrationReceipt({ ...receipt, registered_at: 'invalid' })).toBe(false);
  });
  it('rejects swapped policy kinds, unknown surfaces and malformed references', () => {
    for (const guard of [isRegistrationContext, isRegistrationReceipt]) {
      const base = guard === isRegistrationContext ? context : receipt;
      expect(guard({ ...base, terms: context.privacy })).toBe(false);
      expect(guard({ ...base, privacy: context.terms })).toBe(false);
      expect(guard({ ...base, surface: 'callback' })).toBe(false);
      expect(guard({ ...base, terms: { ...context.terms, version: 1 } })).toBe(false);
    }
  });
});
