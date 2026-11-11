import type { ParamMap } from '@angular/router';
import { instant, uuid } from '../operator-contract';
import { isSupportStatus, isSupportTopic } from './support-contract';
import type { SupportFilters } from './support-contract';

export function supportRoute(params: Readonly<ParamMap>) {
  const caseFilter = params.get('case_id');
  const actor = params.get('actor_id');
  const topic = params.get('topic');
  const status = params.get('status');
  const anonymous = params.get('anonymous');
  const from = params.get('received_from');
  const before = params.get('received_before');
  const cursor = params.get('cursor');
  const caseId = params.get('case');
  const historyOpen = params.get('history') === 'open';
  const historyCursor = params.get('history_cursor');
  const filters: SupportFilters = {
    case_id: caseFilter,
    actor_id: actor,
    topic: isSupportTopic(topic) ? topic : null,
    status: isSupportStatus(status) ? status : null,
    anonymous: anonymous === 'true' ? true : anonymous === 'false' ? false : null,
    received_from: from,
    received_before: before,
    cursor,
  };
  let filterError: string | null = null;
  if ((caseFilter !== null && !uuid(caseFilter)) || (actor !== null && !uuid(actor)))
    filterError = 'Case and account filters must be UUIDs.';
  else if (
    (topic !== null && !isSupportTopic(topic)) ||
    (status !== null && !isSupportStatus(status)) ||
    (anonymous !== null && anonymous !== 'true' && anonymous !== 'false')
  )
    filterError = 'Choose valid topic, status and account filters.';
  else if (actor !== null && anonymous === 'true')
    filterError = 'An anonymous case filter cannot specify an account.';
  else if ((from !== null && !instant(from)) || (before !== null && !instant(before)))
    filterError = 'Received dates must include a valid time and timezone.';
  else if (from !== null && before !== null && Date.parse(from) >= Date.parse(before))
    filterError = 'Received before must be later than Received from.';
  else if (cursor !== null && (cursor.length === 0 || cursor.length > 1024))
    filterError = 'The inbox cursor is invalid. Return to the first page.';
  const caseError =
    caseId !== null && !uuid(caseId) ? 'The selected case ID must be a UUID.' : null;
  const historyError =
    historyCursor !== null && (historyCursor.length === 0 || historyCursor.length > 1024)
      ? 'The history cursor is invalid. Return to the first history page.'
      : null;
  return { filters, caseId, caseError, filterError, historyOpen, historyCursor, historyError };
}
