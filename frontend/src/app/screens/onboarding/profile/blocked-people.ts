import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectorRef,
  Component,
  DestroyRef,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import type { OnChanges } from '@angular/core';
import { TuiButton, TuiLink } from '@taiga-ui/core';
import {
  CancelledError,
  MutationObserver,
  QueryClient,
  QueryObserver,
  queryOptions,
} from '@tanstack/angular-query-experimental';
import type { Mutation, QueryFunctionContext } from '@tanstack/angular-query-experimental';
import type { Api } from '../../../api.generated';
import { ApiFailure, readJson, writeJson } from '../../../api-http';
import { trustedVerifiedActor } from '../../verified-actor';
import { isUncertain } from '../../uncertain';

type Identity = Api['schemas']['IdentityResponse'];
interface Intent {
  readonly actorId: string;
  readonly personId: string;
  readonly key: string;
  readonly body: Api['schemas']['ChangeBlockRequest'];
}
function isBlock(value: unknown): value is Api['schemas']['BlockStateResponse'] {
  return (
    typeof value === 'object' &&
    value !== null &&
    'person_id' in value &&
    typeof value.person_id === 'string' &&
    'blocked' in value &&
    typeof value.blocked === 'boolean' &&
    'version' in value &&
    Number.isSafeInteger(value.version) &&
    typeof value.version === 'number' &&
    value.version >= 0 &&
    'changed_at' in value &&
    (value.changed_at === null || typeof value.changed_at === 'string')
  );
}
function isBlocks(value: unknown): value is Api['schemas']['OwnBlocksResponse'] {
  return (
    typeof value === 'object' &&
    value !== null &&
    'next_cursor' in value &&
    (value.next_cursor === null || typeof value.next_cursor === 'string') &&
    'people' in value &&
    Array.isArray(value.people) &&
    value.people.every(
      (person: unknown) =>
        typeof person === 'object' &&
        person !== null &&
        'block' in person &&
        isBlock(person.block) &&
        person.block.blocked &&
        'deleted' in person &&
        typeof person.deleted === 'boolean' &&
        'display_name' in person &&
        (person.display_name === null || typeof person.display_name === 'string'),
    )
  );
}
@Component({
  selector: 'peerly-blocked-people',
  imports: [TuiButton, TuiLink],
  templateUrl: './blocked-people.html',
})
export class BlockedPeople implements OnChanges {
  public readonly actor = input.required<Identity>();
  public readonly checking = input(false);
  public readonly expired = output();
  private readonly http = inject(HttpClient);
  private readonly client = inject(QueryClient);
  private readonly change = inject(ChangeDetectorRef);
  private readonly destroy = inject(DestroyRef);
  private readonly owner = signal<string | null>(null);
  private readonly cursor = signal<string | null>(null);
  private readonly query = new QueryObserver(this.client, this.options(null, false));
  private readonly scope: object = {};
  private readonly mutation = new MutationObserver(this.client, {
    retry: false,
    meta: { scope: this.scope },
    mutationFn: async (intent: Readonly<Intent>) => {
      const actor = trustedVerifiedActor(this.client, intent.actorId);
      if (actor === null || this.checking() || !this.current(intent.actorId))
        throw new CancelledError();
      const receipt = await writeJson(
        this.http,
        `/api/v1/me/blocks/${encodeURIComponent(intent.personId)}`,
        intent.body,
        { 'x-csrf-token': actor.csrf_token, 'idempotency-key': intent.key },
        isBlock,
        'PUT',
      );
      if (receipt.person_id !== intent.personId || receipt.blocked)
        throw new ApiFailure(0, 'invalid_response', null);
      return receipt;
    },
    onSuccess: async (_receipt, intent: Readonly<Intent>) => {
      if (!this.current(intent.actorId)) return;
      await this.client.invalidateQueries({
        queryKey: ['account', intent.actorId, 'blocks'],
        refetchType: 'none',
      });
      await this.client.invalidateQueries({
        queryKey: ['account', intent.actorId, 'discovery'],
        refetchType: 'none',
      });
      if (trustedVerifiedActor(this.client, intent.actorId) !== null && !this.checking())
        await this.query.refetch();
    },
    onError: (error: unknown, intent: Readonly<Intent>) => {
      if (this.current(intent.actorId)) this.denied(error);
    },
  });
  protected get result() {
    return this.query.getCurrentResult();
  }
  protected get action() {
    return this.mutation.getCurrentResult();
  }
  protected get locked(): boolean {
    return (
      this.checking() ||
      trustedVerifiedActor(this.client, this.actor().account_id) === null ||
      this.action.isPending
    );
  }
  protected get uncertain(): boolean {
    return isUncertain(this.action.error) || this.action.error instanceof CancelledError;
  }
  public constructor() {
    const stopQuery = this.query.subscribe(
      (result: Readonly<ReturnType<typeof this.query.getCurrentResult>>) => {
        this.denied(result.error);
        this.change.markForCheck();
      },
    );
    const stopMutation = this.mutation.subscribe(() => {
      this.change.markForCheck();
    });
    this.destroy.onDestroy(() => {
      stopQuery();
      stopMutation();
      this.query.destroy();
      this.retire();
    });
  }
  public ngOnChanges(): void {
    const id = this.actor().account_id;
    if (this.owner() !== id) {
      this.cursor.set(null);
      this.retire();
      this.owner.set(id);
    }
    this.query.setOptions(
      this.options(id, !this.checking() && trustedVerifiedActor(this.client, id) !== null),
    );
  }
  private retire(): void {
    this.mutation.reset();
    for (const mutation of this.client
      .getMutationCache()
      .findAll({ predicate: (entry: Readonly<Mutation>) => entry.meta?.['scope'] === this.scope }))
      this.client.getMutationCache().remove(mutation);
  }
  private current(id: string): boolean {
    return (
      !this.destroy.destroyed &&
      this.actor().account_id === id &&
      this.client.getQueryData<Identity | null>(['session'])?.account_id === id
    );
  }
  private denied(error: unknown): void {
    if (error instanceof ApiFailure && (error.status === 401 || error.status === 403))
      this.expired.emit();
  }
  private options(id: string | null, enabled: boolean) {
    const cursor = this.cursor();
    return queryOptions({
      queryKey:
        id === null
          ? (['blocked-people-idle'] as const)
          : (['account', id, 'blocks', cursor] as const),
      enabled,
      retry: false,
      staleTime: 0,
      queryFn: ({ signal }: Readonly<QueryFunctionContext>) =>
        readJson(
          this.http,
          `/api/v1/me/blocks${cursor === null ? '' : `?cursor=${encodeURIComponent(cursor)}`}`,
          signal,
          isBlocks,
        ),
    });
  }
  protected async unblock(person: Api['schemas']['BlockedPersonResponse']): Promise<void> {
    if (this.locked || this.action.isError || !this.result.isSuccess || this.result.isFetching)
      return;
    await this.run({
      actorId: this.actor().account_id,
      personId: person.block.person_id,
      key: crypto.randomUUID(),
      body: { blocked: false, expected_version: person.block.version },
    });
  }
  protected async retry(): Promise<void> {
    const intent = this.action.variables;
    if (this.locked || !this.uncertain || intent === undefined) return;
    await this.run(intent);
  }
  private async run(intent: Readonly<Intent>): Promise<void> {
    try {
      await this.mutation.mutate(intent);
    } catch (error: unknown) {
      if (!(error instanceof ApiFailure) && !(error instanceof CancelledError)) throw error;
    }
  }
  protected refresh(): void {
    if (this.locked) return;
    this.mutation.reset();
    void this.query.refetch();
  }
  protected next(): void {
    const cursor = this.result.data?.next_cursor;
    if (this.locked || this.action.isError || cursor === null || cursor === undefined) return;
    this.cursor.set(cursor);
    this.ngOnChanges();
  }
  protected first(): void {
    if (!this.locked && !this.action.isError) {
      this.cursor.set(null);
      this.ngOnChanges();
    }
  }
}
