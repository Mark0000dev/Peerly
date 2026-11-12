import { HttpClient } from '@angular/common/http';
import { ChangeDetectorRef, Component, DestroyRef, inject } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import {
  CancelledError,
  MutationObserver,
  QueryClient,
  QueryObserver,
} from '@tanstack/angular-query-experimental';
import { TuiButton, TuiDialog, TuiLink, TuiAppearance, TUI_BREAKPOINT } from '@taiga-ui/core';
import type { Api } from '../../api.generated';
import { ApiFailure, writeJson } from '../../api-http';
import { TuiAppBar, TuiCardLarge } from '@taiga-ui/layout';
import { PublicHeader } from '../public-header';
import { PublicFooter } from '../public-footer';
import { sessionOptions } from '../session';
import { isDeletionPreparation, isDeletionReceipt } from './deletion-contract';

type Identity = Api['schemas']['IdentityResponse'];
interface Authority {
  readonly actorId: string;
  readonly csrf: string;
}
interface DeleteIntent extends Authority {
  readonly body: Api['paths']['/api/v1/me/deletion']['post']['body'];
  readonly key: string;
}
@Component({
  selector: 'app-delete-account',
  imports: [
    PublicHeader,
    PublicFooter,
    RouterLink,
    TuiButton,
    TuiDialog,
    TuiLink,
    TuiAppearance,
    TuiAppBar,
    TuiCardLarge,
  ],
  templateUrl: './delete-account.html',
  styleUrl: './deletion.less',
})
export class DeleteAccount {
  private readonly http = inject(HttpClient);
  private readonly client = inject(QueryClient);
  private readonly router = inject(Router);
  private readonly change = inject(ChangeDetectorRef);
  private readonly destroy = inject(DestroyRef);
  private readonly owner = {};
  private readonly sessionQuery = new QueryObserver(
    this.client,
    sessionOptions(this.http, this.client),
  );
  private readonly prepareMutation = new MutationObserver(this.client, {
    retry: false,
    meta: { deletionOwner: this.owner },
    mutationFn: (authority: Authority) =>
      writeJson(
        this.http,
        '/api/v1/me/deletion-workflows',
        {},
        { 'X-CSRF-Token': authority.csrf },
        isDeletionPreparation,
      ),
    onSuccess: (_preparation, authority: Authority) => {
      if (this.owns(authority))
        this.client.removeQueries({ queryKey: ['account-deletion-status'] });
    },
    onError: (error: unknown, authority: Authority) => this.expire(error, authority),
  });
  private readonly deleteMutation = new MutationObserver(this.client, {
    retry: false,
    meta: { deletionOwner: this.owner },
    mutationFn: (intent: DeleteIntent) =>
      writeJson(
        this.http,
        '/api/v1/me/deletion',
        intent.body,
        { 'X-CSRF-Token': intent.csrf, 'Idempotency-Key': intent.key },
        (value): value is Api['schemas']['DeletionReceiptResponse'] =>
          isDeletionReceipt(value) && value.workflow_id === intent.body.workflow_id,
      ),
    onSuccess: async (_receipt, intent: DeleteIntent) => {
      if (!this.owns(intent)) return;
      await this.client.cancelQueries({ queryKey: ['account', intent.actorId] });
      if (!this.owns(intent)) return;
      this.client.removeQueries({ queryKey: ['account', intent.actorId] });
      this.client.getMutationCache().clear();
      this.client.setQueryData(['session'], null);
      await this.recovery(intent);
    },
    onError: async (error: unknown, intent: DeleteIntent) => {
      await this.expire(error, intent);
      if (error instanceof ApiFailure) await this.recovery(intent);
    },
  });
  protected get session() {
    return this.sessionQuery.getCurrentResult();
  }
  protected get preparing() {
    return this.prepareMutation.getCurrentResult();
  }
  protected get deleting() {
    return this.deleteMutation.getCurrentResult();
  }
  protected get identity(): Identity | null {
    return this.session.isSuccess && !this.session.isFetching ? this.session.data : null;
  }
  protected readonly breakpoint = inject(TUI_BREAKPOINT);
  protected get publicView(): boolean {
    return (
      this.session.isSuccess &&
      !this.session.isFetching &&
      this.session.data === null &&
      this.deleting.variables === undefined
    );
  }
  protected get confirmation() {
    const actor = this.identity;
    const prepared = this.preparing;
    return this.deleting.variables === undefined &&
      actor !== null &&
      prepared.isSuccess &&
      prepared.variables.actorId === actor.account_id &&
      prepared.variables.csrf === actor.csrf_token
      ? prepared.data
      : null;
  }
  protected get reference(): string | null {
    const error = this.preparing.error ?? this.deleting.error ?? this.session.error;
    return error instanceof ApiFailure ? error.requestId : null;
  }
  public constructor() {
    const update = (): void => {
      this.change.markForCheck();
    };
    const session = this.sessionQuery.subscribe(
      (result: Readonly<ReturnType<typeof this.sessionQuery.getCurrentResult>>) => {
        if (result.isSuccess) {
          const actor = result.data?.account_id;
          const prepared = this.prepareMutation.getCurrentResult().variables;
          if (prepared !== undefined && prepared.actorId !== actor) this.prepareMutation.reset();
          const deletion = this.deleteMutation.getCurrentResult().variables;
          if (actor !== undefined && deletion !== undefined && deletion.actorId !== actor)
            this.deleteMutation.reset();
        }
        update();
      },
    );
    const prepare = this.prepareMutation.subscribe(update);
    const deleting = this.deleteMutation.subscribe(update);
    this.destroy.onDestroy(() => {
      session();
      prepare();
      deleting();
      this.sessionQuery.destroy();
      this.prepareMutation.reset();
      this.deleteMutation.reset();
      for (const mutation of this.client.getMutationCache().getAll())
        if (mutation.options.meta?.['deletionOwner'] === this.owner)
          this.client.getMutationCache().remove(mutation);
    });
  }
  private owns(intent: Authority): boolean {
    const actor = this.client.getQueryData<Identity | null>(['session']);
    return !this.destroy.destroyed && (actor === null || actor?.account_id === intent.actorId);
  }
  private async recovery(intent: Authority): Promise<void> {
    if (this.owns(intent)) await this.router.navigateByUrl('/account/deletion-status');
  }
  private async expire(error: unknown, authority: Authority): Promise<void> {
    if (!(error instanceof ApiFailure) || error.status !== 401 || !this.owns(authority)) return;
    await this.client.cancelQueries({ queryKey: ['account', authority.actorId] });
    if (!this.owns(authority)) return;
    this.client.removeQueries({ queryKey: ['account', authority.actorId] });
    this.client.setQueryData(['session'], null);
  }
  protected checkSession(): void {
    void this.sessionQuery.refetch();
  }
  protected prepare(): void {
    const actor = this.identity;
    if (actor === null || this.preparing.isPending || this.deleting.isPending) return;
    void this.prepareMutation
      .mutate({ actorId: actor.account_id, csrf: actor.csrf_token })
      .catch((error: unknown) => {
        this.handled(error);
      });
  }
  protected keep(): void {
    this.prepareMutation.reset();
  }
  protected confirm(): void {
    const prepared = this.confirmation;
    const actor = this.identity;
    if (prepared === null || actor === null || this.deleting.isPending) return;
    void this.deleteMutation
      .mutate({
        actorId: actor.account_id,
        csrf: actor.csrf_token,
        key: crypto.randomUUID(),
        body: { workflow_id: prepared.workflow_id },
      })
      .catch((error: unknown) => {
        this.handled(error);
      });
  }
  private handled(error: unknown): void {
    if (!(error instanceof ApiFailure) && !(error instanceof CancelledError)) throw error;
  }
}
