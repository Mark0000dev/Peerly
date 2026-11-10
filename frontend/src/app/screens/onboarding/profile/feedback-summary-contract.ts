import type { Api } from '../../../api.generated';

type Building = Api['schemas']['BuildingFeedbackSummaryResponse'];
type Available = Api['schemas']['AvailableFeedbackSummaryResponse'];
function record(value: unknown): value is Readonly<Record<string, unknown>> {
  return typeof value === 'object' && value !== null;
}
function count(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0;
}
export function isBuildingSummary(value: unknown): value is Building {
  return (
    record(value) &&
    (value['state'] === undefined || value['state'] === 'building') &&
    count(value['responses']) &&
    value['responses'] < 3 &&
    typeof value['publicly_visible'] === 'boolean' &&
    !('yes' in value) &&
    !('maybe' in value) &&
    !('no' in value)
  );
}
export function isAvailableSummary(value: unknown): value is Available {
  return (
    record(value) &&
    (value['state'] === undefined || value['state'] === 'available') &&
    count(value['responses']) &&
    value['responses'] >= 3 &&
    typeof value['publicly_visible'] === 'boolean' &&
    count(value['yes']) &&
    count(value['maybe']) &&
    count(value['no']) &&
    value['yes'] + value['maybe'] + value['no'] === value['responses']
  );
}
export function isFeedbackSummary(value: unknown): value is Building | Available {
  return isBuildingSummary(value) || isAvailableSummary(value);
}
