export interface ControlledPeople {
  readonly origin: string;
  readonly cookie_name: string;
  readonly viewer_id: string;
  readonly peer_id: string;
  readonly viewer_session: string;
  readonly peer_session: string;
}
export function isControlledPeople(value: unknown): value is ControlledPeople {
  if (typeof value !== 'object' || value === null) return false;
  return (
    'origin' in value &&
    typeof value.origin === 'string' &&
    /^https:\/\/127\.0\.0\.1:[0-9]{4,5}$/.test(value.origin) &&
    'cookie_name' in value &&
    typeof value.cookie_name === 'string' &&
    /^__Host-[A-Za-z0-9_-]{1,48}$/.test(value.cookie_name) &&
    'viewer_id' in value &&
    typeof value.viewer_id === 'string' &&
    /^[a-f0-9-]{36}$/.test(value.viewer_id) &&
    'peer_id' in value &&
    typeof value.peer_id === 'string' &&
    /^[a-f0-9-]{36}$/.test(value.peer_id) &&
    'viewer_session' in value &&
    typeof value.viewer_session === 'string' &&
    /^[A-Za-z0-9_-]{43}$/.test(value.viewer_session) &&
    'peer_session' in value &&
    typeof value.peer_session === 'string' &&
    /^[A-Za-z0-9_-]{43}$/.test(value.peer_session)
  );
}
