import { provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  ErrorHandler,
  inject,
  provideAppInitializer,
  provideBrowserGlobalErrorListeners,
} from '@angular/core';
import type { ApplicationConfig } from '@angular/core';
import { provideRouter, withRouterConfig } from '@angular/router';
import { provideTaiga } from '@taiga-ui/core';
import { routes } from './app.routes';
import { ObservationErrorHandler } from './observability/observation-errors';
import { observationInterceptor } from './observability/observation-http';
import { NATIVE_RUNTIME } from './native-transport/runtime';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    { provide: ErrorHandler, useClass: ObservationErrorHandler },
    provideHttpClient(
      withInterceptors([
        observationInterceptor,
        (request, next) => {
          const native = inject(NATIVE_RUNTIME);
          return native === null ? next(request) : native.transport.intercept(request, next);
        },
      ]),
    ),
    provideAppInitializer(() => inject(NATIVE_RUNTIME)?.initialize()),
    provideRouter(routes, withRouterConfig({ canceledNavigationResolution: 'computed' })),
    provideTaiga({ mode: 'light' }),
  ],
};
