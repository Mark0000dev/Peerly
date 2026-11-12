/** Resolve the configured application origin, never the request's claimed host. */
export function applicationOrigin(baseURL: string | undefined): string {
  if (baseURL === undefined || !URL.canParse(baseURL))
    throw new Error('Missing or invalid application base URL');
  const application: Readonly<URL> = new URL(baseURL);
  if (
    !['http:', 'https:'].includes(application.protocol) ||
    application.username !== '' ||
    application.password !== ''
  )
    throw new Error('Expected a credential-free HTTP application base URL');
  return application.origin;
}

/** Readonly scenarios allow GET and the required same-origin observation POST only. */
export function isBusinessWrite(
  method: string,
  requestURL: string,
  expectedOrigin: string,
): boolean {
  if (method === 'GET') return false;
  if (method !== 'POST' || !URL.canParse(requestURL)) return true;
  const request: Readonly<URL> = new URL(requestURL);
  return !(
    request.origin === expectedOrigin &&
    request.pathname === '/api/v1/telemetry/events' &&
    request.search === '' &&
    request.hash === '' &&
    request.username === '' &&
    request.password === ''
  );
}
