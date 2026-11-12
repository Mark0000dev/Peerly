import { HttpClient } from '@angular/common/http';
import type { HttpRequest } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import type { TestRequest } from '@angular/common/http/testing';
import { DestroyRef } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { CancelledError, QueryClient } from '@tanstack/angular-query-experimental';
import type { MutationCacheNotifyEvent } from '@tanstack/angular-query-experimental';
import { Subject } from 'rxjs';
import { TuiDialogService } from '@taiga-ui/core';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Api } from '../../../api.generated';
import { appConfig } from '../../../app.config';
import { supportActor, supportCase } from './support.fixtures';
import { SupportStatusEditor } from './support-status';

describe('support status command authorization and resource lifetime', () => {
  let client: QueryClient;
  let backend: HttpTestingController;
  let editor: SupportStatusEditor;
  const selected = supportCase.receipt.case_id;
  const caseKey = [
    'account',
    supportActor.account_id,
    'operator',
    'support',
    'case',
    selected,
  ] as const;
  const refresh = vi.fn(() => Promise.resolve(false));
  const changed = vi.fn(() => Promise.resolve());
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [...appConfig.providers, provideHttpClientTesting()],
    });
    client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
    backend = TestBed.inject(HttpTestingController);
    editor = new SupportStatusEditor(
      TestBed.inject(HttpClient),
      client,
      TestBed.inject(TuiDialogService),
      TestBed.inject(DestroyRef),
      {
        actor: () =>
          client.getQueryData<Api['schemas']['IdentityResponse'] | null>(['session']) ?? null,
        owner: () =>
          client.getQueryData<Api['schemas']['IdentityResponse'] | null>(['session'])?.account_id ??
          null,
        selected: () => selected,
        current: () => {
          const actor = client.getQueryData<Api['schemas']['IdentityResponse'] | null>(['session']);
          return actor === undefined || actor === null
            ? undefined
            : client.getQueryData<Api['schemas']['OperatorSupportResponse']>([
                'account',
                actor.account_id,
                'operator',
                'support',
                'case',
                selected,
              ]);
        },
        refresh,
        changed,
        authorityFailure: vi.fn(),
        mark: vi.fn(),
      },
    );
  });
  afterEach(() => {
    editor.destroy();
    client.clear();
    backend.verify();
    TestBed.resetTestingModule();
    vi.clearAllMocks();
  });
  it('late command callbacks cannot prepare, confirm, replay or reconcile without a trusted actor', async () => {
    editor.form.controls.status.setValue('in_review');
    editor.review();
    editor.confirm();
    editor.replay();
    await editor.useCurrent();
    expect(editor.intent()).toBeNull();
    expect(editor.result.isIdle).toBe(true);
    expect(refresh).not.toHaveBeenCalled();
    expect(changed).not.toHaveBeenCalled();
    backend.expectNone((request: Readonly<HttpRequest<unknown>>) =>
      request.url.startsWith('/api/v1/'),
    );
  });
  it('retiring the editor discards a prepared private command and stale callbacks cannot revive or send it', async () => {
    client.setQueryData(['session'], supportActor);
    client.setQueryData(caseKey, supportCase);
    editor.syncOwner(supportActor.account_id, selected);
    editor.form.controls.status.setValue('in_review');
    editor.review();
    expect(editor.intent()).not.toBeNull();
    editor.destroy();
    editor.review();
    editor.confirm();
    editor.replay();
    await editor.useCurrent();
    expect(editor.intent()).toBeNull();
    expect(editor.result.isIdle).toBe(true);
    expect(refresh).not.toHaveBeenCalled();
    expect(changed).not.toHaveBeenCalled();
    backend.expectNone((request: Readonly<HttpRequest<unknown>>) =>
      request.url.startsWith('/api/v1/'),
    );
  });
  it('a stale confirmation or replay callback cannot send an unconfirmed intent after the canonical version advances', () => {
    client.setQueryData(['session'], supportActor);
    client.setQueryData(caseKey, supportCase);
    editor.syncOwner(supportActor.account_id, selected);
    editor.form.controls.status.setValue('in_review');
    editor.review();
    const prepared = editor.intent();
    expect(prepared).not.toBeNull();
    client.setQueryData(caseKey, {
      ...supportCase,
      receipt: { ...supportCase.receipt, status: 'in_review', version: 4 },
    });
    editor.syncOwner(supportActor.account_id, selected);
    editor.confirm();
    editor.replay();
    expect(editor.intent()).toBe(prepared);
    expect(editor.form.getRawValue()).toEqual({ status: 'in_review', expected_version: 3 });
    expect(editor.result.isIdle).toBe(true);
    expect(changed).not.toHaveBeenCalled();
    backend.expectNone((request: Readonly<HttpRequest<unknown>>) =>
      request.url.startsWith('/api/v1/'),
    );
  });
  function trustedDraft(): void {
    client.setQueryData(['session'], supportActor);
    client.setQueryData(caseKey, supportCase);
    editor.syncOwner(supportActor.account_id, selected);
    editor.form.controls.status.setValue('in_review');
    editor.form.markAsDirty();
  }
  function replacementDraft(): void {
    const actor: Api['schemas']['IdentityResponse'] = {
      ...supportActor,
      account_id: '00000000-0000-4000-8000-000000000099',
      csrf_token: 'replacement-csrf',
    };
    const current: Api['schemas']['OperatorSupportResponse'] = {
      ...supportCase,
      receipt: { ...supportCase.receipt, version: 8, status: 'received' },
    };
    client.setQueryData(
      ['account', actor.account_id, 'operator', 'support', 'case', selected],
      current,
    );
    client.setQueryData(['session'], actor);
    editor.syncOwner(actor.account_id, selected);
    editor.form.controls.status.setValue('resolved');
    editor.form.markAsDirty();
  }
  async function write(): Promise<TestRequest> {
    let result: TestRequest | undefined;
    await vi.waitFor(() => {
      result = backend.expectOne(`/api/v1/operator/cases/${selected}/status`);
    });
    if (result === undefined) throw new Error('Missing explicit status request');
    return result;
  }
  it('logout before the queued mutation starts prevents the actual HTTP dispatch', async () => {
    trustedDraft();
    editor.review();
    editor.confirm();
    client.setQueryData(['session'], null);
    await vi.waitFor(() => {
      expect(editor.result.error).toBeInstanceOf(CancelledError);
    });
    expect(changed).not.toHaveBeenCalled();
    backend.expectNone((request: Readonly<HttpRequest<unknown>>) =>
      request.url.startsWith('/api/v1/'),
    );
  });
  it('actor retirement after a validated receipt prevents a late success callback from changing replacement queries', async () => {
    trustedDraft();
    const detach = client
      .getMutationCache()
      .subscribe((event: Readonly<MutationCacheNotifyEvent>) => {
        if (event.type === 'updated' && event.mutation.state.status === 'success')
          client.setQueryData(['session'], null);
      });
    TestBed.inject(DestroyRef).onDestroy(detach);
    editor.review();
    editor.confirm();
    (await write()).flush({ ...supportCase.receipt, status: 'in_review', version: 4 });
    await vi.waitFor(() => {
      expect(editor.result.isSuccess).toBe(true);
    });
    backend.verify();
    expect(client.getQueryData(['session'])).toBeNull();
    expect(changed).not.toHaveBeenCalled();
    editor.syncOwner(null, selected);
    expect(await editor.canLeave()).toBe(true);
  });
  it('a replacement actor during the fresh-read boundary keeps its own draft and opens no stale confirmation', async () => {
    trustedDraft();
    refresh.mockResolvedValueOnce(true);
    const dialogs = vi.spyOn(TestBed.inject(TuiDialogService), 'open');
    const pending = editor.useCurrent();
    replacementDraft();
    await pending;
    expect(editor.form.getRawValue()).toEqual({ status: 'resolved', expected_version: 8 });
    expect(dialogs).not.toHaveBeenCalled();
    backend.expectNone((request: Readonly<HttpRequest<unknown>>) =>
      request.url.startsWith('/api/v1/'),
    );
  });
  it('a confirmation arriving after actor replacement cannot overwrite the replacement draft', async () => {
    trustedDraft();
    refresh.mockResolvedValueOnce(true);
    const decision = new Subject<boolean>();
    const dialogs = vi
      .spyOn(TestBed.inject(TuiDialogService), 'open')
      .mockReturnValue(decision.asObservable());
    const pending = editor.useCurrent();
    await vi.waitFor(() => {
      expect(dialogs).toHaveBeenCalledOnce();
    });
    replacementDraft();
    decision.next(true);
    decision.complete();
    await pending;
    expect(editor.form.getRawValue()).toEqual({ status: 'resolved', expected_version: 8 });
    expect(editor.intent()).toBeNull();
    backend.expectNone((request: Readonly<HttpRequest<unknown>>) =>
      request.url.startsWith('/api/v1/'),
    );
  });
});
