const dayMilliseconds = 86_400_000;
const kualaLumpurOffset = 8 * 60 * 60 * 1000;
function localDay(time: number): number {
  return Math.floor((time + kualaLumpurOffset) / dayMilliseconds);
}
export function absoluteChatTime(value: string): string {
  return new Intl.DateTimeFormat('en-MY', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'Asia/Kuala_Lumpur',
  }).format(new Date(value));
}
export function chatTime(value: string, now: number): string {
  const timestamp = Date.parse(value);
  const days = localDay(now) - localDay(timestamp);
  if (days === 0)
    return new Intl.DateTimeFormat('en-GB', {
      timeZone: 'Asia/Kuala_Lumpur',
      hour: '2-digit',
      minute: '2-digit',
      hourCycle: 'h23',
    }).format(new Date(timestamp));
  if (days === 1) return 'Yesterday';
  const sameYear =
    new Date(now + kualaLumpurOffset).getUTCFullYear() ===
    new Date(timestamp + kualaLumpurOffset).getUTCFullYear();
  if (days > 1 && days < 7 && sameYear)
    return new Intl.DateTimeFormat('en-GB', {
      timeZone: 'Asia/Kuala_Lumpur',
      weekday: 'short',
    }).format(new Date(timestamp));
  return new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Kuala_Lumpur',
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  }).format(new Date(timestamp));
}
