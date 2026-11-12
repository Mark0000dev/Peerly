import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { ErrorHandler, provideBrowserGlobalErrorListeners } from '@angular/core';
import type { ApplicationConfig } from '@angular/core';
import { provideRouter, withRouterConfig } from '@angular/router';
import { provideTaiga } from '@taiga-ui/core';
import { routes } from './app.routes';
import { ObservationErrorHandler } from './observability/observation-errors';
import { observationInterceptor } from './observability/observation-http';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    { provide: ErrorHandler, useClass: ObservationErrorHandler },
    provideHttpClient(withInterceptors([observationInterceptor])),
    provideRouter(routes, withRouterConfig({ canceledNavigationResolution: 'computed' })),
    provideTaiga({ mode: 'light' }),
  ],
};
