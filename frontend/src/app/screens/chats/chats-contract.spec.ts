import { describe, expect, it } from 'vitest';
import { context, conversation, history, message, page, peer, summary } from './chats.fixtures';
import {
  contextSubject,
  isContext,
  isConversation,
  isConversationList,
  isHistory,
  isMessage,
  isPeer,
  isReadPosition,
  orderedMessages,
  peerName,
} from './chats-contract';

describe('Actual chat read boundary', () => {
  it('accepts genuine nested read projections, never fabricated messages for an empty thread', () => {
    expect(isConversationList(page)).toBe(true);
    expect(isConversation(conversation)).toBe(true);
    expect(isHistory(history)).toBe(true);
    expect(isHistory({ anchor_sequence: 0, messages: [], next_cursor: null })).toBe(true);
    expect(
      isConversationList({ ...page, conversations: [{ ...summary, last_message: null }] }),
    ).toBe(true);
    expect(contextSubject(context)).toBe('Databases');
  });
  it('rejects malformed fields at every nested boundary', () => {
    const read = {
      conversation_id: conversation.conversation_id,
      through_sequence: 1,
      version: 1,
      acknowledged_at: message.sent_at,
    };
    for (const [guard, value] of [
      [isPeer, peer],
      [isMessage, message],
      [isReadPosition, read],
      [isConversation, conversation],
      [isConversationList, page],
      [isHistory, history],
    ] as const) {
      expect(guard(null)).toBe(false);
      expect(guard('wrong')).toBe(false);
      expect(guard(value)).toBe(true);
      for (const key of Object.keys(value)) expect(guard({ ...value, [key]: {} })).toBe(false);
    }
    expect(isConversation({ ...conversation, read_position: read })).toBe(true);
    expect(
      isConversation({ ...conversation, read_position: { ...read, conversation_id: 'foreign' } }),
    ).toBe(false);
    expect(
      isConversation({ ...conversation, read_position: { ...read, through_sequence: 2 } }),
    ).toBe(false);
    expect(isHistory({ ...history, messages: [message, message] })).toBe(false);
    expect(isHistory({ ...history, anchor_sequence: 0 })).toBe(false);
    expect(isMessage({ ...message, sequence: 0 })).toBe(false);
    for (const sequence of [-1, 1.5, Number.NaN, Number.POSITIVE_INFINITY])
      expect(isMessage({ ...message, sequence })).toBe(false);
    expect(isMessage({ ...message, sent_at: 'bad' })).toBe(false);
    expect(
      isConversationList({
        ...page,
        conversations: [{ ...summary, last_message: { ...message, conversation_id: 'foreign' } }],
      }),
    ).toBe(false);
  });
  it('validates all three immutable academic contexts and each nested field', () => {
    expect(isContext(context)).toBe(true);
    expect(
      isContext({
        ...context,
        mode: 'offer_help',
        sender_help: context.recipient_help,
        recipient_goal: context.sender_goal,
        sender_goal: null,
        recipient_help: null,
      }),
    ).toBe(true);
    expect(
      isContext({
        ...context,
        mode: 'study_together',
        recipient_goal: context.sender_goal,
        recipient_help: null,
      }),
    ).toBe(true);
    for (const invalid of [
      null,
      {},
      { ...context, mode: 'wrong' },
      { ...context, sender_goal: null },
    ])
      expect(isContext(invalid)).toBe(false);
    for (const [field, source] of [
      ['sender_goal', context.sender_goal],
      ['recipient_help', context.recipient_help],
    ] as const) {
      if (source === null) throw new Error('Missing fixture context');
      for (const key of Object.keys(source))
        expect(isContext({ ...context, [field]: { ...source, [key]: [] } })).toBe(false);
    }
    expect(
      contextSubject({ ...context, sender_goal: null, recipient_goal: context.sender_goal }),
    ).toBe('Databases');
    expect(contextSubject({ ...context, sender_goal: null })).toBe('');
  });
  it('uses only current peer masking and canonical message sequence, never device time', () => {
    expect(peerName(peer)).toBe('Maya Lim');
    expect(peerName({ ...peer, state: 'unavailable' })).toBe('Profile unavailable');
    expect(peerName({ ...peer, display_name: null })).toBe('Profile unavailable');
    expect(peerName({ ...peer, state: 'deleted' })).toBe('Deleted account');
    expect(isPeer({ ...peer, photo_version: 1 })).toBe(true);
    expect(isPeer({ ...peer, state: 'deleted', display_name: null, photo_version: null })).toBe(
      true,
    );
    const later = { ...message, sequence: 2, sent_at: '2026-11-01T00:00:00Z' };
    expect(orderedMessages([later, message])).toEqual([message, later]);
    expect(orderedMessages([])).toEqual([]);
  });
});
