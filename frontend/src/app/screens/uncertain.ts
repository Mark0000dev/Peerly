import { ApiFailure } from '../api-http';

export function isUncertain(error: unknown): boolean {
  return (
    error instanceof ApiFailure &&
    (error.status === 0 || error.status === 408 || error.status >= 500)
  );
}
