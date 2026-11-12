import { convertToParamMap } from '@angular/router';
import { describe, expect, it } from 'vitest';
import { conversationRoute, isOperatorMessages } from './operator-conversation-contract';
import { conversationId, messagePage, storedMessage } from './operator-conversation.fixtures';

describe('M05 actual retained message contract', () => {
  it('preserves ascending source page, literal text and valid empty anchor', () => {
    expect(isOperatorMessages(messagePage)).toBe(true);
    expect(
      isOperatorMessages({ ...messagePage, anchor_sequence: 0, messages: [], next_cursor: null }),
    ).toBe(true);
    expect(
      isOperatorMessages({
        ...messagePage,
        messages: Array.from({ length: 50 }, (_, i) => storedMessage(i + 1)),
      }),
    ).toBe(true);
  });
  it('accepts current nullable image-only message metadata without weakening retained identifiers', () => {
    const image = {
      ...storedMessage(1),
      text: null,
      image_id: '00000000-0000-4000-8000-000000000099',
    };
    expect(isOperatorMessages({ ...messagePage, messages: [image] })).toBe(true);
    expect(
      isOperatorMessages({ ...messagePage, messages: [{ ...image, image_id: 'invalid' }] }),
    ).toBe(false);
    expect(isOperatorMessages({ ...messagePage, messages: [{ ...image, image_id: null }] })).toBe(
      false,
    );
  });
  it('rejects malformed metadata, foreign authors/conversations and reordered or duplicate messages', () => {
    for (const bad of [
      null,
      {},
      { ...messagePage, low_id: messagePage.high_id },
      { ...messagePage, anchor_sequence: -1 },
      { ...messagePage, anchor_sequence: 1.5 },
      { ...messagePage, accepted_request_version: 0 },
      { ...messagePage, next_cursor: 4 },
      { ...messagePage, messages: Array.from({ length: 51 }, (_, i) => storedMessage(i + 1)) },
      { ...messagePage, messages: [storedMessage(54)] },
      { ...messagePage, messages: [storedMessage(2), storedMessage(1)] },
      {
        ...messagePage,
        messages: [
          storedMessage(1),
          { ...storedMessage(2), message_id: storedMessage(1).message_id },
        ],
      },
    ])
      expect(isOperatorMessages(bad)).toBe(false);
    for (const field of ['conversation_id', 'relationship_id', 'request_id', 'low_id', 'high_id'])
      expect(isOperatorMessages({ ...messagePage, [field]: 'bad' })).toBe(false);
    for (const [field, value] of Object.entries({
      message_id: 'bad',
      client_message_id: 'bad',
      conversation_id: messagePage.request_id,
      author_id: messagePage.request_id,
      sequence: 0,
      text: null,
      sent_at: 'bad',
    }))
      expect(
        isOperatorMessages({ ...messagePage, messages: [{ ...storedMessage(1), [field]: value }] }),
      ).toBe(false);
  });
  it('validates URL selection and opaque cursor without inventing a list lookup', () => {
    expect(conversationRoute(convertToParamMap({}))).toEqual({
      id: null,
      cursor: null,
      error: null,
    });
    expect(
      conversationRoute(convertToParamMap({ conversation: conversationId, cursor: 'opaque' }))
        .error,
    ).toBeNull();
    for (const params of [
      { conversation: 'bad' },
      { cursor: 'opaque' },
      { conversation: conversationId, cursor: '' },
      { conversation: conversationId, cursor: 'x'.repeat(1025) },
    ])
      expect(conversationRoute(convertToParamMap(params)).error).not.toBeNull();
  });
});
