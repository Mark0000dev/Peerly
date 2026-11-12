import type { Api } from '../../api.generated';
export const conversationId = 'a1111111-1111-4111-8111-111111111111';
export const otherConversationId = 'a2222222-2222-4222-8222-222222222222';
const lowId = 'b1111111-1111-4111-8111-111111111111';
const highId = 'c1111111-1111-4111-8111-111111111111';
export function storedMessage(sequence: number): Api['schemas']['MessageResponse'] {
  const suffix = String(sequence).padStart(12, '0');
  return {
    message_id: `d1111111-1111-4111-8111-${suffix}`,
    client_message_id: `e1111111-1111-4111-8111-${suffix}`,
    conversation_id: conversationId,
    author_id: sequence % 2 === 0 ? highId : lowId,
    sequence,
    image_id: null,
    text:
      sequence === 53
        ? "Stored literal <script>alert('not executable')</script>\n  Original spacing"
        : `Retained message ${String(sequence)}`,
    sent_at: '2026-01-08T04:00:00Z',
  };
}
export const messagePage: Api['schemas']['OperatorMessagesResponse'] = {
  conversation_id: conversationId,
  relationship_id: 'f1111111-1111-4111-8111-111111111111',
  request_id: 'f2222222-2222-4222-8222-222222222222',
  low_id: lowId,
  high_id: highId,
  accepted_request_version: 2,
  anchor_sequence: 53,
  messages: [storedMessage(52), storedMessage(53)],
  next_cursor: 'signed-older-page',
};
