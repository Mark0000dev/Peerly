import { HttpClient } from '@angular/common/http';
import { ChangeDetectorRef, Component, DestroyRef, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import {
  CancelledError,
  QueryClient,
  QueryObserver,
  queryOptions,
} from '@tanstack/angular-query-experimental';
import type { QueryFunctionContext } from '@tanstack/angular-query-experimental';
import { TuiButton, TuiLink } from '@taiga-ui/core';
import { ApiFailure, readJson } from '../../api-http';
import { TuiBlockStatus } from '@taiga-ui/layout';
import { PublicHeader } from '../public-header';
import { PublicFooter } from '../public-footer';
import { sessionOptions } from '../session';
import { isConfirmedDeletion, isDeletionStatus } from './deletion-contract';

@Component({
  selector: 'app-deletion-status',
  imports: [PublicHeader, PublicFooter, TuiBlockStatus, RouterLink, TuiButton, TuiLink],
  templateUrl: './deletion-status.html',
  styleUrl: './deletion.less',
})
export class DeletionStatus {
  private readonly http = inject(HttpClient);
  private readonly client = inject(QueryClient);
  private readonly change = inject(ChangeDetectorRef);
  private readonly destroy = inject(DestroyRef);
  // Recovery uses the server's HttpOnly proof cookie, independently of /me.
  // Never put the proof, workflow ID or session credentials in a route.
  private readonly query = new QueryObserver(
    this.client,
    queryOptions({
      queryKey: ['account-deletion-status'] as const,
      retry: false,
      staleTime: 0,
      refetchOnMount: 'always',
      refetchOnWindowFocus: false,
      refetchOnReconnect: false,
      queryFn: ({ signal }: Readonly<QueryFunctionContext>) =>
        readJson(this.http, '/api/v1/me/deletion-status', signal, isDeletionStatus),
    }),
  );

  protected get status() {
    return this.query.getCurrentResult();
  }
  protected get confirmed(): boolean {
    return (
      this.status.isSuccess && !this.status.isFetching && isConfirmedDeletion(this.status.data)
    );
  }
  protected get unavailable(): boolean {
    return this.status.error instanceof ApiFailure && this.status.error.status === 404;
  }
  protected get reference(): string | null {
    return this.status.error instanceof ApiFailure ? this.status.error.requestId : null;
  }
  public constructor() {
    const unsubscribe = this.query.subscribe(
      (result: Readonly<ReturnType<typeof this.query.getCurrentResult>>) => {
        if (result.isSuccess && !result.isFetching && isConfirmedDeletion(result.data)) {
          // The destructive response may have been lost. Recheck ordinary session
          // authority without making proof recovery depend on a live session, and
          // without clearing a newer live account because an older proof remains.
          void this.client.query(sessionOptions(this.http, this.client)).catch((error: unknown) => {
            if (!(error instanceof ApiFailure) && !(error instanceof CancelledError)) throw error;
          });
        }
        this.change.markForCheck();
      },
    );
    this.destroy.onDestroy(() => {
      unsubscribe();
      this.query.destroy();
      this.client.removeQueries({ queryKey: ['account-deletion-status'], type: 'inactive' });
    });
  }
  protected check(): void {
    void this.query.refetch();
  }
}
