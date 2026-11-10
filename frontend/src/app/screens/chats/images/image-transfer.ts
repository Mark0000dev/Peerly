import { HttpErrorResponse } from '@angular/common/http';
import type { HttpClient } from '@angular/common/http';
import type { Api } from '../../../api.generated';
import { ApiFailure, writeJson } from '../../../api-http';

function isAccess(value: unknown): value is Api['schemas']['ImageUploadAccessResponse'] {
  if (
    typeof value !== 'object' ||
    value === null ||
    !('url' in value) ||
    typeof value.url !== 'string' ||
    !('fields' in value) ||
    typeof value.fields !== 'object' ||
    value.fields === null ||
    Array.isArray(value.fields) ||
    !Object.values(value.fields).every((entry: unknown) => typeof entry === 'string')
  )
    return false;
  try {
    const url = new URL(value.url);
    return (
      (url.protocol === 'https:' || url.protocol === 'http:') &&
      url.username === '' &&
      url.password === ''
    );
  } catch {
    return false;
  }
}

// A signed ticket is private transport material. It never leaves this stack or
// enters Query/Mutation results, error text, logging or browser persistence.
export async function transferImage(
  http: Readonly<HttpClient>,
  conversationId: string,
  imageId: string,
  csrf: string,
  file: Readonly<Blob>,
  signal: Readonly<AbortSignal>,
): Promise<void> {
  signal.throwIfAborted();
  const access = await writeJson(
    http,
    `/api/v1/conversations/${encodeURIComponent(conversationId)}/image-preparations/${encodeURIComponent(imageId)}/upload-access`,
    undefined,
    { 'x-csrf-token': csrf },
    isAccess,
  );
  signal.throwIfAborted();
  const form = new FormData();
  for (const [key, value] of Object.entries(access.fields)) form.append(key, value);
  form.append('file', file, 'image');
  await new Promise<void>((resolve, reject) => {
    const request = http
      .post(access.url, form, {
        observe: 'response',
        responseType: 'text',
        credentials: 'omit',
        withCredentials: false,
        redirect: 'error',
        referrerPolicy: 'no-referrer',
        referrer: '',
      })
      .subscribe({
        next: () => {
          signal.removeEventListener('abort', abort);
          resolve();
        },
        error: (error: unknown) => {
          signal.removeEventListener('abort', abort);
          reject(
            new ApiFailure(
              error instanceof HttpErrorResponse ? error.status : 0,
              'image_transfer_unknown',
              null,
            ),
          );
        },
      });
    function abort(): void {
      request.unsubscribe();
      reject(new DOMException('Transfer cancelled', 'AbortError'));
    }
    signal.addEventListener('abort', abort, { once: true });
    if (signal.aborted) abort();
  });
}
