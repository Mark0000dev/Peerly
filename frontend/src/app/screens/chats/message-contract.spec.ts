import { FormControl } from '@angular/forms';
import { describe, expect, it } from 'vitest';
import { message } from './chats.fixtures';
import {
  isOperation,
  isTerminalOperation,
  messageProblem,
  messageValidator,
} from './message-contract';

describe('C02 actual immutable message outcomes and raw text', () => {
  const confirmed = {
    operation_id: 'op',
    conversation_id: message.conversation_id,
    client_message_id: message.client_message_id,
    message,
  };
  const cancelled = {
    operation_id: 'op',
    conversation_id: message.conversation_id,
    client_message_id: message.client_message_id,
    cancelled_at: message.sent_at,
  };
  const unobserved = {
    conversation_id: message.conversation_id,
    client_message_id: message.client_message_id,
  };
  it('accepts actual image-only/captioned confirmations and rejects malformed or empty content', () => {
    const image = { ...message, text: null, image_id: '00000000-0000-4000-8000-000000000099' };
    expect(isTerminalOperation({ ...confirmed, message: image })).toBe(true);
    expect(isTerminalOperation({ ...confirmed, message: { ...image, text: 'Caption' } })).toBe(
      true,
    );
    for (const invalid of [
      { ...image, image_id: null },
      { ...image, image_id: undefined },
      { ...image, image_id: '' },
      { ...image, image_id: 'not-an-image-id' },
      { ...image, image_id: 3 },
      { ...image, text: 3 },
    ])
      expect(isTerminalOperation({ ...confirmed, message: invalid })).toBe(false);
  });
  it('supports omitted default discriminators without confusing unobserved with cancelled', () => {
    expect(isOperation(confirmed)).toBe(true);
    expect(isOperation(cancelled)).toBe(true);
    expect(isOperation(unobserved)).toBe(true);
    expect(isTerminalOperation(unobserved)).toBe(false);
    expect(isOperation({ ...confirmed, outcome: 'confirmed' })).toBe(true);
    expect(isOperation({ ...cancelled, outcome: 'cancelled' })).toBe(true);
    expect(isOperation({ ...unobserved, outcome: 'unobserved' })).toBe(true);
    for (const value of [confirmed, cancelled, unobserved]) {
      for (const key of Object.keys(value))
        expect(isOperation({ ...value, [key]: [] })).toBe(false);
      expect(isOperation({ ...value, outcome: ['confirmed'] })).toBe(false);
    }
    expect(isOperation(null)).toBe(false);
    expect(isOperation({})).toBe(false);
    expect(isOperation({ ...confirmed, cancelled_at: message.sent_at })).toBe(false);
    expect(
      isOperation({ ...confirmed, message: { ...message, client_message_id: 'foreign' } }),
    ).toBe(false);
    expect(isOperation({ ...confirmed, message: { ...message, conversation_id: 'foreign' } })).toBe(
      false,
    );
    expect(isOperation({ ...cancelled, cancelled_at: 'bad' })).toBe(false);
    expect(isOperation({ ...unobserved, cancelled_at: message.sent_at })).toBe(false);
  });
  it('counts Unicode codepoints, keeps raw intent and rejects malformed control text', () => {
    expect(messageProblem('')).toBe('Enter a message.');
    expect(messageProblem('\n \t')).toBe('Enter a message.');
    expect(messageProblem('😀'.repeat(2000))).toBeNull();
    expect(messageProblem('😀'.repeat(2001))).toBe('Use at most 2000 characters.');
    expect(messageProblem(' hello\n\tworld ')).toBeNull();
    expect(messageProblem('x\u0000')).toBe('Remove unsupported control characters.');
    expect(messageProblem('x\ud800')).toBe('Remove unsupported control characters.');
    const control = new FormControl(' raw text ', { nonNullable: true });
    expect(messageValidator(control)).toBeNull();
    expect(control.value).toBe(' raw text ');
    control.setValue('');
    expect(messageValidator(control)).toEqual({ message: 'Enter a message.' });
  });
});
