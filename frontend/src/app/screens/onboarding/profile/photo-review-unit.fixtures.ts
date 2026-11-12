import { HttpResponse, provideHttpClient, withInterceptors } from '@angular/common/http';
import type { HttpHandlerFn, HttpRequest } from '@angular/common/http';
import type { EnvironmentProviders } from '@angular/core';
import { of } from 'rxjs';
import { noPhotoReview } from './photo-review.fixtures';

// Explicit ordinary-profile UNIT fixture, not a production/default browser fallback.
// Dedicated recovery tests retain the real HttpTestingController response boundary.
export function provideNoPhotoReview(): EnvironmentProviders {
  return provideHttpClient(
    withInterceptors([
      (request: Readonly<HttpRequest<unknown>>, next: HttpHandlerFn) =>
        request.method === 'GET' && request.url === '/api/v1/me/photo-review'
          ? of(new HttpResponse({ status: 200, body: noPhotoReview }))
          : next(request),
    ]),
  );
}
