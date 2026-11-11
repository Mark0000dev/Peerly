import { describe, expect, it } from 'vitest';
import { isAccount, isAccounts, isDetail, instant, uuid } from './operator-contract';
import { account, accounts, detail, nullableDetail } from './operator.fixtures';

describe('Privileged account nested response boundary', () => {
  it('accepts actual complete and absent records and retained lifecycle states', () => {
    expect(isAccounts(accounts)).toBe(true);
    expect(isDetail(detail)).toBe(true);
    expect(isDetail(nullableDetail)).toBe(true);
    expect(
      isDetail({
        ...detail,
        account: {
          ...account,
          banned_at: account.created_at,
          deleted_at: account.created_at,
          hidden_at: account.created_at,
          membership: { ...account.membership, revoked_at: account.created_at },
        },
      }),
    ).toBe(true);
    expect(
      isDetail({
        ...detail,
        profile: {
          ...detail.profile,
          display_name: null,
          about: null,
          programme: null,
          year_label: null,
          languages: [],
          task: 'offer_help',
        },
        goal: {
          ...detail.goal,
          subject: { kind: 'custom', label: 'Personal topic' },
          completed_at: account.created_at,
          topic: null,
          context: null,
        },
        exposure: { ...detail.exposure, paused_at: account.created_at },
        lifecycle: { ...detail.lifecycle, hidden_at: account.created_at },
      }),
    ).toBe(true);
    expect(
      isDetail({ ...detail, goal: { ...detail.goal, subject: { label: 'Personal topic' } } }),
    ).toBe(true);
    expect(
      isDetail({
        ...detail,
        goal: { ...detail.goal, subject: { id: account.account_id, label: 'Canonical topic' } },
      }),
    ).toBe(true);
    for (const kind of [
      'profile_revision',
      'photo_revision',
      'goal_revision',
      'help_revision',
      'registration_receipt',
    ])
      expect(isDetail({ ...detail, links: [{ kind, id: account.account_id, version: 1 }] })).toBe(
        true,
      );
    expect(uuid(null)).toBe(false);
    expect(instant(null)).toBe(false);
    expect(instant('2026-01-01T00:00:00')).toBe(false);
  });
  it('rejects malformed account fields and page boundaries without hiding missing stored data', () => {
    expect(isAccount(null)).toBe(false);
    expect(isAccounts(null)).toBe(false);
    expect(isAccounts({ ...accounts, next_cursor: 3 })).toBe(false);
    expect(isAccounts({ ...accounts, accounts: {} })).toBe(false);
    for (const key of Object.keys(account))
      expect(isAccount({ ...account, [key]: undefined })).toBe(false);
    expect(isAccount({ ...account, profile_version: 0 })).toBe(false);
    expect(isAccount({ ...account, profile_version: 1.5 })).toBe(false);
    expect(isAccount({ ...account, created_at: 'bad' })).toBe(false);
    for (const value of [null, 4, 'invalid', {}]) {
      expect(isAccount({ ...account, google_link: value })).toBe(value === null);
      expect(isAccount({ ...account, membership: value })).toBe(value === null);
    }
    for (const key of Object.keys(account.google_link ?? {}))
      expect(
        isAccount({ ...account, google_link: { ...account.google_link, [key]: undefined } }),
      ).toBe(false);
    for (const key of Object.keys(account.membership ?? {}))
      expect(
        isAccount({ ...account, membership: { ...account.membership, [key]: undefined } }),
      ).toBe(false);
  });
  it('rejects every missing nested privileged field and invalid discriminator/collection element', () => {
    expect(isDetail(null)).toBe(false);
    for (const key of Object.keys(detail))
      expect(isDetail({ ...detail, [key]: undefined })).toBe(false);
    for (const key of [
      'profile',
      'goal',
      'help_subjects',
      'photo',
      'lifecycle',
      'exposure',
      'registration',
    ] as const) {
      const value = detail[key];
      for (const field of Object.keys(value ?? {}))
        expect(isDetail({ ...detail, [key]: { ...value, [field]: undefined } })).toBe(false);
    }
    expect(isDetail({ ...detail, profile: { ...detail.profile, languages: [3] } })).toBe(false);
    expect(isDetail({ ...detail, profile: { ...detail.profile, task: 'unknown' } })).toBe(false);
    expect(
      isDetail({ ...detail, goal: { ...detail.goal, subject: { id: 3, label: 'Unknown' } } }),
    ).toBe(false);
    expect(
      isDetail({
        ...detail,
        goal: { ...detail.goal, subject: { kind: 'invalid', label: 'Unknown' } },
      }),
    ).toBe(false);
    expect(
      isDetail({
        ...detail,
        goal: {
          ...detail.goal,
          subject: { id: account.account_id, kind: 'custom', label: 'Unknown' },
        },
      }),
    ).toBe(false);
    expect(
      isDetail({ ...detail, help_subjects: { ...detail.help_subjects, subjects: [null] } }),
    ).toBe(false);
    for (const field of ['subject_id', 'label', 'topic_note'])
      expect(
        isDetail({
          ...detail,
          help_subjects: {
            ...detail.help_subjects,
            subjects: [
              {
                subject_id: account.account_id,
                label: 'Python',
                topic_note: null,
                [field]: undefined,
              },
            ],
          },
        }),
      ).toBe(false);
    expect(isDetail({ ...detail, exposure: { ...detail.exposure, inactivity_seconds: 0 } })).toBe(
      false,
    );
    expect(
      isDetail({ ...detail, exposure: { ...detail.exposure, inactivity_seconds: Infinity } }),
    ).toBe(false);
    expect(
      isDetail({ ...detail, registration: { ...detail.registration, surface: 'other' } }),
    ).toBe(false);
    for (const link of [
      null,
      { kind: 'unknown', id: account.account_id, version: 1 },
      { kind: 'goal_revision', id: 'bad', version: 1 },
      { kind: 'goal_revision', id: account.account_id, version: 0 },
    ])
      expect(isDetail({ ...detail, links: [link] })).toBe(false);
  });
});
