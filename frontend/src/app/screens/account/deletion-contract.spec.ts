import { describe, expect, it } from 'vitest';
import {
  isConfirmedDeletion,
  isDeletionPreparation,
  isDeletionReceipt,
  isDeletionStatus,
} from './deletion-contract';

const preparation = {
  workflow_id: '11111111-1111-4111-8111-111111111111',
  expires_at: '2026-11-09T10:00:00Z',
} as const;
const receipt = {
  workflow_id: preparation.workflow_id,
  deleted_at: '2026-11-09T09:00:00Z',
  source_version: 1,
} as const;

describe('P05 actual deletion proof contracts', () => {
  it('accepts preparation without treating it as a committed deletion', () => {
    expect(isDeletionPreparation(preparation)).toBe(true);
    expect(isDeletionStatus(preparation)).toBe(true);
    expect(isDeletionStatus({ ...preparation, state: 'pending' })).toBe(true);
    expect(isConfirmedDeletion(preparation)).toBe(false);
    expect(isDeletionReceipt(preparation)).toBe(false);
  });
  it('accepts actual receipt and optional default discriminator', () => {
    expect(isDeletionReceipt(receipt)).toBe(true);
    expect(isDeletionStatus(receipt)).toBe(true);
    expect(isConfirmedDeletion({ ...receipt, state: 'deleted' })).toBe(true);
  });
  it.each([
    null,
    [],
    'deleted',
    {},
    { ...preparation, workflow_id: 'not-a-proof' },
    { ...preparation, expires_at: 'invalid' },
    { ...preparation, state: 'deleted' },
    { ...preparation, deleted_at: receipt.deleted_at },
    { ...preparation, source_version: 1 },
    { ...receipt, state: 'pending' },
    { ...receipt, expires_at: preparation.expires_at },
    { ...receipt, deleted_at: 1 },
    { ...receipt, source_version: 0 },
    { ...receipt, source_version: 1.5 },
    { ...receipt, source_version: Number.MAX_SAFE_INTEGER + 1 },
    { ...receipt, workflow_id: null },
  ])('rejects malformed or contradictory status %#', (value: unknown) => {
    expect(isDeletionStatus(value)).toBe(false);
  });
});
