import { HttpClient } from '@angular/common/http';
import { ChangeDetectorRef, Component, DestroyRef, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { TuiButton, TuiLink } from '@taiga-ui/core';
import type { Query } from '@tanstack/angular-query-experimental';
import { QueryClient, QueryObserver } from '@tanstack/angular-query-experimental';
import { ApiFailure } from '../../../api-http';
import { sessionOptions } from '../../session';
import { supportStatus } from './support-contract';
import { recentSupportOptions, supportActor } from './support-query';

@Component({
  selector: 'app-support-recovery',
  imports: [DatePipe, RouterLink, TuiButton, TuiLink],
  templateUrl: './support-recovery.html',
  styleUrl: './support.less',
})
export class SupportRecovery {
  private readonly http = inject(HttpClient);
  private readonly client = inject(QueryClient);
  private readonly change = inject(ChangeDetectorRef);
  private readonly destroy = inject(DestroyRef);
  protected readonly anonymous = signal(false);
  private readonly session = new QueryObserver(this.client, sessionOptions(this.http, this.client));
  private readonly query = new QueryObserver(
    this.client,
    recentSupportOptions(this.http, null, false),
  );
  protected readonly statusLabel = supportStatus;
  protected get result() {
    return this.query.getCurrentResult();
  }
  protected get checkingIdentity(): boolean {
    return !this.anonymous() && supportActor(this.client) === undefined;
  }
  protected get unavailable(): boolean {
    return (
      this.result.error instanceof ApiFailure && this.result.error.code === 'support_unavailable'
    );
  }
  protected get reference(): string | null {
    return this.result.error instanceof ApiFailure ? this.result.error.requestId : null;
  }
  public constructor() {
    const unsubscribeSession = this.session.subscribe(() => {
      this.bind();
      this.change.markForCheck();
    });
    const unsubscribeQuery = this.query.subscribe(() => {
      this.change.markForCheck();
    });
    this.destroy.onDestroy(() => {
      unsubscribeSession();
      unsubscribeQuery();
      this.session.destroy();
      this.query.destroy();
      this.client.removeQueries({ queryKey: ['support-recovery'], type: 'inactive' });
      this.client.removeQueries({
        predicate: (query: Readonly<Query>) => query.queryKey[2] === 'support-recovery',
        type: 'inactive',
      });
    });
  }
  private bind(): void {
    const actor = supportActor(this.client);
    this.query.setOptions(
      recentSupportOptions(
        this.http,
        this.anonymous() ? null : (actor?.account_id ?? null),
        this.anonymous() || actor !== undefined,
      ),
    );
  }
  protected recoverAnonymous(): void {
    this.anonymous.set(true);
    this.bind();
  }
  protected recoverActor(): void {
    this.anonymous.set(false);
    this.bind();
  }
  protected refresh(): void {
    if (!this.checkingIdentity) void this.query.refetch();
  }
  protected checkIdentity(): void {
    void this.session.refetch();
  }
}
