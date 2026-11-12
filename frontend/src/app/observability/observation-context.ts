import { HttpContextToken } from '@angular/common/http';
import type { ActionHandle } from './observation-contract';
// Caller keeps this immutable logical handle across its explicit same-intent retries.
// It is never inferred from form data, URL IDs, body or an Idempotency-Key.
export const CLIENT_ACTION = new HttpContextToken<ActionHandle | null>(() => null);
