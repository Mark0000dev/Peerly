import type { HttpClient } from '@angular/common/http';
import { ApiFailure, writeJson } from '../../../../api-http';
import { isUploadAccess } from './photo-contract';

// Sensitive transport tickets live only inside this call. Never return them to a Query/Mutation
// observer, persist them, or include provider details in an application error.
export async function transferPhoto(
  http: Readonly<HttpClient>,
  uploadId: string,
  csrf: string,
  file: Readonly<Blob>,
  signal: Readonly<AbortSignal>,
  permitted: () => boolean,
): Promise<void> {
  signal.throwIfAborted();
  if (!permitted()) throw new DOMException('Photo transfer paused for sign-in', 'AbortError');
  const access = await writeJson(
    http,
    `/api/v1/media/uploads/${encodeURIComponent(uploadId)}/access`,
    undefined,
    { 'x-csrf-token': csrf },
    isUploadAccess,
  );
  signal.throwIfAborted();
  if (!permitted()) throw new DOMException('Photo transfer paused for sign-in', 'AbortError');
  const form = new FormData();
  for (const [key, value] of Object.entries(access.fields)) form.append(key, value);
  form.append('file', file, 'photo');
  let result: Response;
  try {
    result = await fetch(access.url, {
      method: 'POST',
      body: form,
      credentials: 'omit',
      redirect: 'error',
      referrerPolicy: 'no-referrer',
      signal,
    });
  } catch (error: unknown) {
    if (signal.aborted) throw new DOMException('Transfer cancelled', 'AbortError');
    if (error instanceof TypeError) throw new ApiFailure(0, 'photo_transfer_unknown', null);
    throw error;
  }
  if (!result.ok) throw new ApiFailure(result.status, 'photo_transfer_failed', null);
}
