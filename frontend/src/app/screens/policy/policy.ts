import { isPolicyReference } from '../policy-reference';
import { PublicHeader } from '../public-header';
import { PublicFooter } from '../public-footer';
import { HttpClient } from '@angular/common/http';
import { Component, ChangeDetectorRef, DestroyRef, inject } from '@angular/core';
import { DatePipe } from '@angular/common';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { TuiButton, TuiLink, TuiLoader } from '@taiga-ui/core';
import { QueryClient, QueryObserver, queryOptions } from '@tanstack/angular-query-experimental';
import type { QueryFunctionContext } from '@tanstack/angular-query-experimental';
import { ApiFailure, readJson } from '../../api-http';
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

function isHistory(value: unknown): value is Api['schemas']['PolicyHistoryResponse'] {
  if (
    typeof value !== 'object' ||
    value === null ||
    !('items' in value) ||
    !Array.isArray(value.items) ||
    value.items.length > 20 ||
    !('next_cursor' in value)
  )
    return false;
  return (
    (value.next_cursor === null ||
      (typeof value.next_cursor === 'string' &&
        value.next_cursor.length > 0 &&
        value.next_cursor.length <= 256)) &&
    value.items.every(
      (item: unknown) =>
        typeof item === 'object' &&
        item !== null &&
        'title' in item &&
        typeof item.title === 'string' &&
        'reference' in item &&
        isPolicyReference(item.reference),
    )
  );
}

@Component({
  selector: 'app-policy',
  imports: [PublicHeader, PublicFooter, DatePipe, RouterLink, TuiButton, TuiLink, TuiLoader],
  template: `<peerly-public-header />
    <main>
      <nav aria-label="Documents">
        <a tuiLink routerLink="/terms">Terms of Use</a> ·
        <a tuiLink routerLink="/privacy">Privacy Policy</a>
      </nav>
      <nav aria-label="Document versions">
        <a tuiLink [routerLink]="path">Latest document</a>
        <a tuiLink [routerLink]="path" [queryParams]="{ view: 'history' }">Version history</a>
      </nav>
      @if (historyView) {
        <h1>{{ title }} · Version history</h1>
        @if (historyState.isPending) {
          <tui-loader [loading]="true" textContent="Loading published versions…" role="status" />
        } @else if (historyState.data; as history) {
          <ul class="versions">
            @for (item of history.items; track item.reference.id) {
              <li>
                <a tuiLink [routerLink]="path" [queryParams]="{ version: item.reference.version }"
                  >{{ item.title }} · {{ item.reference.version }}</a
                >
                <p class="metadata">
                  Published {{ item.reference.published_at | date: 'longDate' }}
                </p>
              </li>
            } @empty {
              <li>No published versions are available.</li>
            }
          </ul>
          @if (history.next_cursor; as cursor) {
            <a
              tuiButton
              appearance="secondary"
              [routerLink]="path"
              [queryParams]="{ view: 'history', cursor }"
              >Older versions</a
            >
          }
        } @else if (historyCursorInvalid) {
          <p role="alert">This version-history page link can’t be used.</p>
          <a
            tuiButton
            appearance="secondary"
            [routerLink]="path"
            [queryParams]="{ view: 'history' }"
            >Latest published versions</a
          >
        } @else {
          <p role="alert">Published versions could not be loaded.</p>
          <button tuiButton type="button" (click)="retryHistory()">Try again</button>
        }
      } @else if (state.isPending) {
        <tui-loader [loading]="true" textContent="Loading document…" role="status" />
      } @else if (state.data; as document) {
        <article aria-labelledby="document-title">
          <h1 id="document-title">{{ document.title }}</h1>
          <p class="metadata">
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
    </main>
    <peerly-public-footer />`,
  styles: `
    main {
      max-inline-size: 48rem;
      margin-inline: auto;
      padding: 2rem max(1.5rem, env(safe-area-inset-right)) 3rem
        max(1.5rem, env(safe-area-inset-left));
      min-block-size: 60dvh;
      overflow-wrap: anywhere;
    }
    nav {
      display: flex;
      gap: 1rem;
      align-items: center;
      flex-wrap: wrap;
      font: var(--tui-typography-body-s);
    }
    .versions {
      display: grid;
      gap: 1.5rem;
      padding-inline-start: 1.5rem;
    }
    .metadata {
      font: var(--tui-typography-body-s);
      color: var(--tui-text-secondary);
    }

    .document {
      white-space: pre-wrap;
      margin-block: 2rem;
      font: var(--tui-typography-body-l);
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
  private readonly historyQuery = new QueryObserver(this.client, this.historyOptions());
  protected readonly path = `/${this.kind}`;
  protected get historyView(): boolean {
    return this.route.snapshot.queryParamMap.get('view') === 'history';
  }
  protected get historyState() {
    return this.historyQuery.getCurrentResult();
  }
  protected get historyCursorInvalid(): boolean {
    return this.historyState.error instanceof ApiFailure && this.historyState.error.status === 422;
  }
  protected readonly title = this.kind === 'privacy' ? 'Privacy Policy' : 'Terms of Use';
  protected get state() {
    return this.query.getCurrentResult();
  }
  public constructor() {
    const unsubscribe = this.query.subscribe(() => {
      this.change.markForCheck();
    });
    const unsubscribeHistory = this.historyQuery.subscribe(() => {
      this.change.markForCheck();
    });
    this.destroy.onDestroy(() => {
      unsubscribeHistory();
      this.historyQuery.destroy();
      unsubscribe();
      this.query.destroy();
    });
    this.route.queryParamMap.pipe(takeUntilDestroyed()).subscribe((params) => {
      this.query.setOptions(this.options(params.get('version')));
      this.historyQuery.setOptions(this.historyOptions());
    });
  }
  private options(version: string | null) {
    const suffix = version === null ? '' : `?version=${encodeURIComponent(version)}`;
    return queryOptions({
      queryKey: ['policy', this.kind, version] as const,
      enabled: !this.historyView,
      queryFn: ({ signal }: Readonly<QueryFunctionContext>) =>
        readJson(this.http, `/api/v1/policies/${this.kind}${suffix}`, signal, isDocument),
      retry: false,
    });
  }
  private historyOptions() {
    const cursor = this.route.snapshot.queryParamMap.get('cursor');
    const params = new URLSearchParams({ limit: '20' });
    if (cursor !== null) params.set('cursor', cursor);
    return queryOptions({
      queryKey: ['policy-history', this.kind, cursor] as const,
      enabled: this.historyView,
      queryFn: ({ signal }: Readonly<QueryFunctionContext>) =>
        readJson(
          this.http,
          `/api/v1/policies/${this.kind}/versions?${params.toString()}`,
          signal,
          (value): value is Api['schemas']['PolicyHistoryResponse'] =>
            isHistory(value) && value.items.every((item) => item.reference.kind === this.kind),
        ),
      retry: false,
    });
  }
  protected retryHistory(): void {
    void this.historyQuery.refetch();
  }
  protected retry(): void {
    void this.query.refetch();
  }
}
