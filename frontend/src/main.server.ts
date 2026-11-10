import { provideUniversal } from '@ng-web-apis/universal';
import { mergeApplicationConfig } from '@angular/core';
import { bootstrapApplication } from '@angular/platform-browser';
import type { BootstrapContext } from '@angular/platform-browser';
import { provideServerRendering, withRoutes, RenderMode } from '@angular/ssr';
import { App } from './app/app';
import { appConfig } from './app/app.config';

export default (context: Readonly<BootstrapContext>) =>
  bootstrapApplication(
    App,
    mergeApplicationConfig(appConfig, {
      providers: [
        provideUniversal(),
        provideServerRendering(
          withRoutes([
            { path: '', renderMode: RenderMode.Prerender },
            { path: '**', renderMode: RenderMode.Client },
          ]),
        ),
      ],
    }),
    context,
  );
