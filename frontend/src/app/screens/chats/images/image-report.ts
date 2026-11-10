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
import type { OnChanges, OnInit } from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule } from '@angular/forms';
import type { AbstractControl } from '@angular/forms';
import { TuiButton, TuiRadio, TuiTextfield } from '@taiga-ui/core';
import { TuiTextarea } from '@taiga-ui/kit/components/textarea';
import {
  CancelledError,
  MutationObserver,
  QueryClient,
} from '@tanstack/angular-query-experimental';
import type { Api } from '../../../api.generated';
import type { QueryCacheNotifyEvent } from '@tanstack/angular-query-experimental';
import { ApiFailure, writeJson } from '../../../api-http';
import { isUncertain } from '../../uncertain';
import { trustedChatActor } from '../chats-session';
import { isImageReportContext, isImageReportReceipt } from './image-contract';

interface Owner {
  readonly actorId: string;
  readonly message: Api['schemas']['MessageResponse'];
  readonly lifetime: object;
}
interface ReportIntent extends Owner {
  readonly key: string;
  readonly body: Api['schemas']['MessageImageReportRequest'];
}

@Component({
  selector: 'app-chat-image-report',
  imports: [ReactiveFormsModule, TuiButton, TuiRadio, TuiTextfield, TuiTextarea],
  templateUrl: './image-report.html',
  styleUrl: './image-report.less',
})
export class ImageReport implements OnInit, OnChanges {
  public readonly actorId = input.required<string>();
  public readonly message = input.required<Api['schemas']['MessageResponse']>();
  public readonly sessionFailure = output<ApiFailure>();
  private readonly http = inject(HttpClient);
  private readonly client = inject(QueryClient);
  private readonly change = inject(ChangeDetectorRef);
  private readonly destroy = inject(DestroyRef);
  private readonly lifetime = signal<object>({});
  private readonly mutationOwner: object = {};
  protected readonly expanded = signal(false);
  protected readonly commentId = `image-report-${crypto.randomUUID()}`;
  protected readonly categories: Readonly<Record<Api['schemas']['ReportCategory'], string>> = {
    impersonation: 'Impersonation',
    harassment: 'Harassment',
    inappropriate_content: 'Inappropriate content',
    spam: 'Spam',
    other: 'Other',
  };
  protected readonly choices: readonly (readonly [string, string])[] = Object.entries(
    this.categories,
  );
  protected readonly form = new FormGroup({
    category: new FormControl<Api['schemas']['ReportCategory'] | null>(
      null,
      (control: Readonly<AbstractControl<unknown>>) =>
        control.value === null ? { required: true } : null,
    ),
    comment: new FormControl('', {
      nonNullable: true,
      validators: [
        (control: Readonly<AbstractControl<string>>) =>
          Array.from(control.value).length > 1000 ? { maxlength: true } : null,
      ],
    }),
  });
  private readonly contextMutation = new MutationObserver(this.client, {
    mutationKey: ['chat-image-report-context'],
    meta: { chatImages: this.mutationOwner },
    retry: false,
    mutationFn: async (owner: Owner) => {
      const actor = this.authority(owner);
      const value = await writeJson(
        this.http,
        `/api/v1/conversations/${encodeURIComponent(owner.message.conversation_id)}/messages/${encodeURIComponent(owner.message.message_id)}/report-contexts`,
        undefined,
        { 'x-csrf-token': actor.csrf_token },
        (candidate): candidate is Api['schemas']['MessageImageReportContextResponse'] =>
          isImageReportContext(candidate) &&
          candidate.conversation_id === owner.message.conversation_id &&
          candidate.message_id === owner.message.message_id &&
          candidate.image_id === owner.message.image_id,
      );
      this.authority(owner);
      return value;
    },
  });
  private readonly submitMutation = new MutationObserver(this.client, {
    mutationKey: ['chat-image-report'],
    meta: { chatImages: this.mutationOwner },
    retry: false,
    mutationFn: async (intent: ReportIntent) => {
      const actor = this.authority(intent);
      const value = await writeJson(
        this.http,
        '/api/v1/reports',
        intent.body,
        { 'x-csrf-token': actor.csrf_token, 'Idempotency-Key': intent.key },
        (candidate): candidate is Api['schemas']['MessageImageReportReceipt'] =>
          isImageReportReceipt(candidate) && candidate.context_id === intent.body.context_id,
      );
      this.authority(intent);
      return value;
    },
  });
  protected get context() {
    return this.contextMutation.getCurrentResult();
  }
  protected get submission() {
    return this.submitMutation.getCurrentResult();
  }
  protected get uncertain(): boolean {
    return this.submission.isError && isUncertain(this.submission.error);
  }
  protected get eligible(): boolean {
    return (
      this.message().image_id !== null &&
      this.message().author_id !== this.actorId() &&
      trustedChatActor(this.client, this.actorId()) !== null
    );
  }
  public ngOnInit(): void {
    const context = this.contextMutation.subscribe(() => {
      this.settled();
    });
    const submit = this.submitMutation.subscribe(() => {
      this.settled();
    });
    const session = this.client
      .getQueryCache()
      .subscribe((event: Readonly<QueryCacheNotifyEvent>) => {
        const key: unknown = event.query.queryKey;
        if (Array.isArray(key) && key[0] === 'session' && !this.eligible) this.retire();
      });
    this.destroy.onDestroy(() => {
      this.retire();
      context();
      submit();
      session();
      for (const mutation of this.client.getMutationCache().getAll()) {
        if (mutation.options.meta?.['chatImages'] === this.mutationOwner)
          this.client.getMutationCache().remove(mutation);
      }
    });
  }
  public ngOnChanges(): void {
    const owner = this.context.variables ?? this.submission.variables;
    if (
      owner !== undefined &&
      (owner.actorId !== this.actorId() ||
        owner.message.conversation_id !== this.message().conversation_id ||
        owner.message.message_id !== this.message().message_id ||
        owner.message.image_id !== this.message().image_id)
    )
      this.retire();
  }
  private retire(): void {
    this.lifetime.set({});
    this.expanded.set(false);
    this.contextMutation.reset();
    this.submitMutation.reset();
    this.form.reset();
  }
  private authority(owner: Owner): Api['schemas']['IdentityResponse'] {
    const actor = trustedChatActor(this.client, owner.actorId);
    if (
      actor === null ||
      owner.lifetime !== this.lifetime() ||
      owner.actorId !== this.actorId() ||
      owner.message.message_id !== this.message().message_id ||
      owner.message.conversation_id !== this.message().conversation_id ||
      !this.eligible
    )
      throw new CancelledError();
    return actor;
  }
  private settled(): void {
    if (this.destroy.destroyed) return;
    this.change.markForCheck();
    const error = this.context.error ?? this.submission.error;
    if (
      error instanceof ApiFailure &&
      (error.status === 401 || error.status === 403) &&
      this.eligible
    )
      this.sessionFailure.emit(error);
  }
  protected begin(): void {
    if (!this.eligible || this.context.isPending) return;
    this.expanded.set(true);
    const owner: Owner = {
      actorId: this.actorId(),
      message: this.message(),
      lifetime: this.lifetime(),
    };
    void this.contextMutation.mutate(owner).catch(() => undefined);
  }
  protected close(): void {
    if (this.context.isPending || this.submission.isPending || this.uncertain) return;
    this.retire();
  }
  protected submit(): void {
    if (!this.eligible || this.submission.isPending || this.submission.isSuccess) return;
    const previous = this.submission.variables;
    if (this.submission.isError && previous !== undefined) {
      void this.submitMutation.mutate(previous).catch(() => undefined);
      return;
    }
    this.form.markAllAsTouched();
    const category = this.form.controls.category.value;
    const comment = this.form.controls.comment.value.trim();
    const context = this.context.data;
    if (
      this.form.invalid ||
      category === null ||
      context === undefined ||
      (category === 'other' && comment.length === 0)
    )
      return;
    const intent: ReportIntent = {
      actorId: this.actorId(),
      message: this.message(),
      lifetime: this.lifetime(),
      key: crypto.randomUUID(),
      body: {
        context_id: context.id,
        kind: 'message_image',
        category,
        comment: comment.length === 0 ? null : comment,
      },
    };
    void this.submitMutation.mutate(intent).catch(() => undefined);
  }
  protected restart(): void {
    if (this.submission.isPending || this.uncertain) return;
    this.retire();
    this.begin();
  }
}
