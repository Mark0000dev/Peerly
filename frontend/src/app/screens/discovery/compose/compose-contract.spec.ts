import { FormControl } from '@angular/forms';
import { describe, expect, it } from 'vitest';
import {
  contextBelongsTo,
  isAcademicContext,
  isPreview,
  isPreviewResult,
  isSendResult,
  requestParameters,
  requestTextProblem,
  requestTextValidator,
  codePoints,
  sameContext,
} from './compose-contract';
import { actor, recipientId, preview, receipt, connected } from './compose.fixtures';

describe('D03 actual retained previews and pair outcomes', () => {
  for (const mode of ['find_help', 'offer_help', 'study_together'] as const)
    it(`${mode} accepts only its actual academic structure and matching participants`, () => {
      const value = preview(mode);
      expect(isPreview(value)).toBe(true);
      expect(isPreviewResult(value)).toBe(true);
      expect(isAcademicContext(value.context)).toBe(true);
      expect(
        contextBelongsTo(value.context, { actorId: actor.account_id, recipientId, mode }),
      ).toBe(true);
      expect(contextBelongsTo(value.context, { actorId: recipientId, recipientId, mode })).toBe(
        false,
      );
      expect(
        contextBelongsTo(value.context, {
          actorId: actor.account_id,
          recipientId: actor.account_id,
          mode,
        }),
      ).toBe(false);
      expect(
        contextBelongsTo(value.context, {
          actorId: actor.account_id,
          recipientId,
          mode: mode === 'find_help' ? 'offer_help' : 'find_help',
        }),
      ).toBe(false);
      expect(isAcademicContext({ ...value.context, mode: 'unknown' })).toBe(false);
      expect(isAcademicContext({ ...value.context, mode: ['find_help'] })).toBe(false);
      for (const key of ['sender_goal', 'sender_help', 'recipient_goal', 'recipient_help'])
        expect(isAcademicContext({ ...value.context, [key]: {} })).toBe(false);
    });
  it('validates nested goal/help fields without claiming private profile access', () => {
    const value = preview();
    const goal = value.context.sender_goal;
    const help = value.context.recipient_help;
    if (goal === null || help === null) throw new Error('Missing synthetic source');
    for (const key of Object.keys(goal))
      expect(isAcademicContext({ ...value.context, sender_goal: { ...goal, [key]: [] } })).toBe(
        false,
      );
    for (const key of Object.keys(help))
      expect(isAcademicContext({ ...value.context, recipient_help: { ...help, [key]: [] } })).toBe(
        false,
      );
    expect(isAcademicContext({ ...value.context, sender_goal: { ...goal, version: 0 } })).toBe(
      false,
    );
    expect(isAcademicContext({ ...value.context, recipient_help: { ...help, version: 1.2 } })).toBe(
      false,
    );
    const shared = preview('study_together');
    expect(
      isAcademicContext({ ...shared.context, sender_goal: { ...goal, shared_learning: false } }),
    ).toBe(false);
    expect(
      isAcademicContext({
        ...shared.context,
        recipient_goal: { ...goal, subject_id: 'different', shared_learning: true },
      }),
    ).toBe(false);
  });
  it('supports optional wire discriminators but rejects ambiguous or coercible shapes', () => {
    expect(isPreview({ ...preview(), outcome: undefined })).toBe(true);
    expect(isPreview({ ...preview(), outcome: ['preview'] })).toBe(false);
    expect(isSendResult({ ...connected, outcome: undefined })).toBe(true);
    expect(isSendResult({ ...connected, version: 1, outcome: undefined })).toBe(false);
    expect(isSendResult({ ...connected, preview_id: 'unexpected' })).toBe(false);
    expect(isSendResult({ ...connected, outcome: ['connected'] })).toBe(false);
    expect(isSendResult({ ...connected, conversation_id: null })).toBe(false);
    expect(isPreviewResult(receipt)).toBe(false);
    expect(isPreviewResult({ ...receipt, outcome: 'incoming' })).toBe(true);
    expect(isPreviewResult({ ...receipt, outcome: 'existing_outgoing' })).toBe(true);
    expect(isPreviewResult(connected)).toBe(true);
    expect(isSendResult(receipt)).toBe(true);
    expect(isSendResult({ ...receipt, outcome: 'accepted' })).toBe(false);
    expect(isSendResult({ ...receipt, outcome: ['sent'] })).toBe(false);
  });
  for (const invalid of [null, undefined, '', 1, [], {}, true])
    it(`rejects non-contract payload ${JSON.stringify(invalid)}`, () => {
      expect(isAcademicContext(invalid)).toBe(false);
      expect(isPreview(invalid)).toBe(false);
      expect(isSendResult(invalid)).toBe(false);
      expect(isPreviewResult(invalid)).toBe(false);
    });
  it('rejects malformed preview and social receipts instead of fabricating a success', () => {
    for (const key of ['created_at', 'context', 'preview_id'])
      expect(isPreview({ ...preview(), [key]: 0 })).toBe(false);
    expect(isPreview({ ...preview(), created_at: 'not-a-date' })).toBe(false);
    for (const key of Object.keys(receipt))
      expect(isSendResult({ ...receipt, [key]: [] })).toBe(false);
    for (const value of [-1, 0, Number.NaN, Number.POSITIVE_INFINITY, Number.MAX_SAFE_INTEGER + 1])
      expect(isSendResult({ ...receipt, version: value })).toBe(false);
    expect(isSendResult({ ...receipt, undo_until: 'not-a-date' })).toBe(false);
    expect(isSendResult({ ...receipt, changed_at: 'not-a-date' })).toBe(false);
  });
  it('existing pairs navigate only to actual owned Requests resources', () => {
    expect(requestParameters(receipt)).toEqual({ request: receipt.request_id, box: 'sent' });
    expect(requestParameters({ ...receipt, outcome: 'existing_outgoing' })).toEqual({
      request: receipt.request_id,
      box: 'sent',
    });
    expect(requestParameters({ ...receipt, outcome: 'incoming' })).toEqual({
      request: receipt.request_id,
      box: 'received',
    });
    expect(requestParameters(connected)).toEqual({ request: receipt.request_id });
    expect(
      requestParameters({
        request_id: connected.request_id,
        conversation_id: connected.conversation_id,
      }),
    ).toEqual({
      request: receipt.request_id,
    });
  });
  it('validates actual advisory quota/capability fields without inferring sendability', () => {
    const value = preview();
    for (const key of [
      'suggested_text',
      'checked_at',
      'quota',
      'can_send',
      'block_reason',
      'cooldown_until',
    ])
      expect(isPreview({ ...value, [key]: [] })).toBe(false);
    for (const key of Object.keys(value.quota))
      expect(isPreview({ ...value, quota: { ...value.quota, [key]: -1 } })).toBe(false);
    expect(isPreview({ ...value, quota: { ...value.quota, outgoing_pending_limit: 0 } })).toBe(
      false,
    );
    expect(isPreview({ ...value, quota: { ...value.quota, daily_send_limit: 0 } })).toBe(false);
    expect(isPreview({ ...value, checked_at: 'invalid' })).toBe(false);
    expect(isPreview({ ...value, suggested_text: '' })).toBe(false);
    expect(isPreview({ ...value, can_send: false })).toBe(false);
    expect(isPreview({ ...value, cooldown_until: value.checked_at })).toBe(false);
    for (const block_reason of [
      'existing_outgoing',
      'incoming',
      'connected',
      'source_changed',
      'unavailable',
      'outgoing_pending_limit',
      'daily_send_limit',
    ] as const)
      expect(isPreview({ ...value, block_reason, can_send: false })).toBe(true);
    expect(
      isPreview({
        ...value,
        block_reason: 'cooldown',
        can_send: false,
        cooldown_until: value.checked_at,
      }),
    ).toBe(true);
    expect(isPreview({ ...value, block_reason: 'cooldown', can_send: false })).toBe(false);
    expect(isPreview({ ...value, block_reason: ['unavailable'], can_send: false })).toBe(false);
    // Availability is authoritative even if counters appear exhausted or another policy denies it.
    expect(isPreview({ ...value, quota: { ...value.quota, daily_sends_remaining: 0 } })).toBe(true);
  });
  it('compares the actual entire academic source including labels, not merely preview IDs', () => {
    const first = preview().context;
    const other = preview('offer_help').context;
    expect(sameContext(first, first)).toBe(true);
    expect(sameContext(other, other)).toBe(true);
    expect(sameContext(preview('study_together').context, preview('study_together').context)).toBe(
      true,
    );
    expect(sameContext(first, other)).toBe(false);
    expect(sameContext(first, { ...first, sender_goal: null })).toBe(false);
    expect(sameContext({ ...first, sender_goal: null }, first)).toBe(false);
    expect(sameContext(first, { ...first, recipient_help: null })).toBe(false);
    expect(sameContext({ ...first, recipient_help: null }, first)).toBe(false);
    expect(
      sameContext(first, {
        ...first,
        sender_goal: {
          ...first.sender_goal,
          owner_id: 'changed',
          goal_id: 'changed',
          version: 2,
          subject_id: 'changed',
          subject_label: 'Updated',
          topic: null,
          context: null,
          shared_learning: false,
        },
      }),
    ).toBe(false);
    expect(
      sameContext(first, {
        ...first,
        recipient_help: {
          owner_id: recipientId,
          version: 1,
          subject_id: 'changed',
          subject_label: 'Updated',
          topic_note: null,
        },
      }),
    ).toBe(false);
  });
});

describe('D03 bounded Unicode form values', () => {
  it('accepts240 emoji code points and keeps241 unchanged with a useful error', () => {
    expect(codePoints('🙂'.repeat(240))).toBe(240);
    expect(requestTextProblem('🙂'.repeat(240), true)).toBeNull();
    expect(requestTextProblem('🙂'.repeat(241), true)).toContain('not been cut');
    expect(requestTextProblem('Text\nwith\ttabs', true)).toBeNull();
  });
  it('requires actual request text, permits empty optional note, rejects unsafe controls', () => {
    expect(requestTextProblem('', true)).toContain('Write a request');
    expect(requestTextProblem(' \n\t ', true)).toContain('Write a request');
    expect(requestTextProblem('', false)).toBeNull();
    for (const value of ['Text\u0000', 'Text\u0007', 'Text\r', '\ud800'])
      expect(requestTextProblem(value, true)).toContain('control characters');
  });
  it('uses the typed form validator without UTF16 maxlength or silent normalization', () => {
    const required = requestTextValidator(true);
    const optional = requestTextValidator(false);
    expect(required(new FormControl('🙂'.repeat(240), { nonNullable: true }))).toBeNull();
    expect(required(new FormControl(''))).toEqual({
      requestText: 'Write a request before sending.',
    });
    expect(optional(new FormControl(''))).toBeNull();
    expect(optional(new FormControl(null))).toEqual({ requestText: 'Enter plain text.' });
    expect(optional(new FormControl('a'.repeat(241)))).toEqual({
      requestText: 'Keep this field within 240 characters. Your text has not been cut.',
    });
  });
});
