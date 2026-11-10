import { isPolicyReference } from '../policy-reference';
import { Brand } from '../brand';
import { HttpClient } from '@angular/common/http';
import { Component, ChangeDetectorRef, DestroyRef, inject } from '@angular/core';
import { DatePipe } from '@angular/common';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { TuiButton, TuiLink, TuiLoader } from '@taiga-ui/core';
import { QueryClient, QueryObserver, queryOptions } from '@tanstack/angular-query-experimental';
import type { QueryFunctionContext } from '@tanstack/angular-query-experimental';
import { readJson } from '../../api-http';
import type { Api } from '../../api.generated';

type Document = Api['schemas']['PublishedPolicyResponse'];

function isDocument(value: unknown): value is Document {
  if (typeof value !== 'object' || value === null) return false;
  if (
    !('title' in value) ||
    typeof value.title !== 'string' ||
    !('content' in value) ||
    typeof value.content !== 'string' ||
    !('reference' in value) ||
    typeof value.reference !== 'object' ||
    value.reference === null
  )
    return false;
  return isPolicyReference(value.reference);
}

@Component({
  selector: 'app-policy',
  imports: [Brand, DatePipe, RouterLink, TuiButton, TuiLink, TuiLoader],
  template: `<main>
    <header><peerly-brand /><a tuiButton routerLink="/onboarding">Open the app</a></header>
    <nav aria-label="Documents">
      <a tuiLink routerLink="/terms">Terms of Use</a> ·
      <a tuiLink routerLink="/privacy">Privacy Policy</a>
    </nav>
    @if (state.isPending) {
      <tui-loader [loading]="true" textContent="Loading document…" role="status" />
    } @else if (state.data; as document) {
      <article>
        <h1>{{ document.title }}</h1>
        <p>
          Version {{ document.reference.version }} · Published
          {{ document.reference.published_at | date: 'longDate' }}
        </p>
        <div class="document">{{ document.content }}</div>
      </article>
    } @else {
      <section>
        <h1>{{ title }}</h1>
        <p role="alert">This document is not available right now.</p>
        <button tuiButton type="button" (click)="retry()">Try again</button>
      </section>
    }
  </main>`,
  styles: `
    main {
      max-inline-size: 50rem;
      margin-inline: auto;
      padding: 1.5rem;
      overflow-wrap: anywhere;
    }
    header {
      display: flex;
      gap: 1rem;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      margin-block-end: 2rem;
    }

    .document {
      white-space: pre-wrap;
      margin-block: 2rem;
    }
    h1 {
      font: var(--tui-typography-heading-h3);
      margin-block: 2rem 1rem;
    }
  `,
})
export class Policy {
  private readonly http = inject(HttpClient);
  private readonly client = inject(QueryClient);
  private readonly route = inject(ActivatedRoute);
  private readonly change = inject(ChangeDetectorRef);
  private readonly destroy = inject(DestroyRef);
  private readonly kind: 'terms' | 'privacy' =
    this.route.snapshot.routeConfig?.path === 'privacy' ? 'privacy' : 'terms';
  private readonly query = new QueryObserver(
    this.client,
    this.options(this.route.snapshot.queryParamMap.get('version')),
  );
  protected readonly title = this.kind === 'privacy' ? 'Privacy Policy' : 'Terms of Use';
  protected get state() {
    return this.query.getCurrentResult();
  }
  public constructor() {
    const unsubscribe = this.query.subscribe(() => {
      this.change.markForCheck();
    });
    this.destroy.onDestroy(() => {
      unsubscribe();
      this.query.destroy();
    });
    this.route.queryParamMap.pipe(takeUntilDestroyed()).subscribe((params) => {
      this.query.setOptions(this.options(params.get('version')));
    });
  }
  private options(version: string | null) {
    const suffix = version === null ? '' : `?version=${encodeURIComponent(version)}`;
    return queryOptions({
      queryKey: ['policy', this.kind, version] as const,
      queryFn: ({ signal }: Readonly<QueryFunctionContext>) =>
        readJson(this.http, `/api/v1/policies/${this.kind}${suffix}`, signal, isDocument),
      retry: false,
    });
  }
  protected retry(): void {
    void this.query.refetch();
  }
}
