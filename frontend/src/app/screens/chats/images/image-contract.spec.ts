import { describe, expect, it } from 'vitest';
import {
  imageSelectionProblem,
  imageSource,
  isImagePreparation,
  isImagePreparations,
  isImageReceipt,
  isImageReportContext,
  isImageReportReceipt,
  isImageSource,
  sameImageSource,
} from './image-contract';

const uuid = '11111111-1111-4111-8111-111111111111';
const stamp = '2026-11-08T08:00:00Z';
const source = { content_type: 'image/png', sha256: 'a'.repeat(64), size: 3 } as const;
const preparation = {
  client_message_id: uuid,
  conversation_id: uuid,
  image_id: uuid,
  created_at: stamp,
  updated_at: stamp,
  upload_expires_at: stamp,
  processing_expires_at: stamp,
  display: null,
  expected_source: source,
  failure: null,
  message_outcome: null,
  source_state: 'processing',
  state: 'processing',
  source_version: 1,
} as const;

describe('C03 actual image boundaries', () => {
  it('validates native selection without network access or extension guesses', () => {
    expect(imageSelectionProblem(new Blob(['a'], { type: 'image/png' }))).toBeNull();
    expect(imageSelectionProblem(new Blob(['a'], { type: 'image/jpeg' }))).toBeNull();
    expect(imageSelectionProblem(new Blob(['a'], { type: 'image/gif' }))).toContain('JPEG or PNG');
    expect(imageSelectionProblem(new Blob([], { type: 'image/png' }))).toContain('not empty');
    expect(
      imageSelectionProblem(new Blob([new Uint8Array(10_000_000)], { type: 'image/png' })),
    ).toBeNull();
    expect(
      imageSelectionProblem(new Blob([new Uint8Array(10_000_001)], { type: 'image/png' })),
    ).toContain('10 MB');
  });
  it('hashes the actual bytes and detects changed source despite identical size and type', async () => {
    const original = await imageSource(new Blob(['abc'], { type: 'image/png' }));
    expect(original).toEqual({
      content_type: 'image/png',
      size: 3,
      sha256: 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad',
    });
    expect(
      sameImageSource(original, await imageSource(new Blob(['abc'], { type: 'image/png' }))),
    ).toBe(true);
    expect(
      sameImageSource(original, await imageSource(new Blob(['abd'], { type: 'image/png' }))),
    ).toBe(false);
    expect(sameImageSource(original, { ...original, size: 4 })).toBe(false);
    expect(sameImageSource(original, { ...original, content_type: 'image/jpeg' })).toBe(false);
    await expect(imageSource(new Blob(['abc']))).rejects.toThrow('Unsupported image type');
  });
  it('rejects malformed sources and does not confuse historical receipt with canonical state', () => {
    expect(isImageSource(source)).toBe(true);
    for (const bad of [
      null,
      [],
      {},
      { ...source, content_type: 'image/gif' },
      { ...source, sha256: 'A'.repeat(64) },
      { ...source, sha256: null },
      { ...source, size: 0 },
      { ...source, size: 10_000_001 },
      { ...source, size: 1.5 },
    ])
      expect(isImageSource(bad)).toBe(false);
    const receipt = {
      client_message_id: uuid,
      conversation_id: uuid,
      image_id: uuid,
      receipt_state: 'ready',
      receipt_version: 2,
    };
    expect(isImageReceipt(receipt)).toBe(true);
    expect(isImagePreparation(receipt)).toBe(false);
    expect(isImageReceipt({ ...receipt, receipt_version: 0 })).toBe(false);
    expect(isImageReceipt({ ...receipt, image_id: 'bad' })).toBe(false);
    expect(isImageReceipt({ ...receipt, receipt_state: 'sent' })).toBe(false);
  });
  it('keeps effective and source states distinct, accepts actual outcome and metadata', () => {
    expect(isImagePreparation(preparation)).toBe(true);
    for (const state of [
      'uploading',
      'queued',
      'processing',
      'ready',
      'rejected',
      'cancelled',
      'expired',
    ])
      expect(isImagePreparation({ ...preparation, state, source_state: 'ready' })).toBe(true);
    for (const failure of [
      'invalid_image',
      'unsupported_format',
      'too_large',
      'dimensions_exceeded',
      'animated_image',
      'content_changed',
      'account_unavailable',
      'contact_unavailable',
      'storage_unavailable',
      'processing_unavailable',
    ])
      expect(isImagePreparation({ ...preparation, failure })).toBe(true);
    for (const outcome of ['confirmed', 'cancelled'])
      expect(
        isImagePreparation({
          ...preparation,
          display: { width: 1, height: 1, size: 1 },
          message_outcome: {
            attachment_confirmed: true,
            message_id: uuid,
            operation_id: uuid,
            outcome,
          },
        }),
      ).toBe(true);
    expect(
      isImagePreparation({
        ...preparation,
        message_outcome: {
          attachment_confirmed: false,
          message_id: null,
          operation_id: uuid,
          outcome: 'cancelled',
        },
      }),
    ).toBe(true);
    for (const patch of [
      { created_at: 'bad' },
      { updated_at: null },
      { upload_expires_at: false },
      { processing_expires_at: '' },
      { failure: 'invented' },
      { source_state: 'sent' },
      { source_version: -1 },
      { state: null },
      { display: {} },
      { display: { width: 0, height: 1, size: 1 } },
      { display: { width: 1, height: 0, size: 1 } },
      { display: { width: 1, height: 1, size: 0 } },
      { expected_source: {} },
      { conversation_id: null },
      { client_message_id: null },
      { image_id: null },
      { message_outcome: {} },
      {
        message_outcome: {
          attachment_confirmed: true,
          message_id: 'bad',
          operation_id: uuid,
          outcome: 'confirmed',
        },
      },
      {
        message_outcome: {
          attachment_confirmed: true,
          message_id: null,
          operation_id: 'bad',
          outcome: 'confirmed',
        },
      },
      {
        message_outcome: {
          attachment_confirmed: true,
          message_id: null,
          operation_id: uuid,
          outcome: 'ready',
        },
      },
    ])
      expect(isImagePreparation({ ...preparation, ...patch })).toBe(false);
    expect(isImagePreparations({ preparations: [preparation] })).toBe(true);
    expect(isImagePreparations({ preparations: [] })).toBe(true);
    expect(isImagePreparations({ preparations: [null] })).toBe(false);
    expect(isImagePreparations(null)).toBe(false);
    expect(isImagePreparations({ preparations: null })).toBe(false);
  });
  it('accepts only actual message-image report contexts and receipts', () => {
    const context = {
      id: uuid,
      conversation_id: uuid,
      message_id: uuid,
      image_id: uuid,
      issued_at: stamp,
    };
    const receipt = { id: uuid, context_id: uuid, submitted_at: stamp };
    expect(isImageReportContext(context)).toBe(true);
    expect(isImageReportContext({ ...context, kind: 'message_image' })).toBe(true);
    expect(isImageReportReceipt(receipt)).toBe(true);
    expect(isImageReportReceipt({ ...receipt, kind: 'message_image' })).toBe(true);
    for (const patch of [
      { id: null },
      { conversation_id: 'bad' },
      { image_id: 'bad' },
      { message_id: 'bad' },
      { issued_at: 'bad' },
      { kind: 'profile' },
    ])
      expect(isImageReportContext({ ...context, ...patch })).toBe(false);
    for (const patch of [
      { id: null },
      { context_id: 'bad' },
      { submitted_at: 'bad' },
      { kind: 'profile' },
    ])
      expect(isImageReportReceipt({ ...receipt, ...patch })).toBe(false);
    expect(isImageReportContext(null)).toBe(false);
    expect(isImageReportReceipt(null)).toBe(false);
  });
});
