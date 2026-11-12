import { NativeImage } from '../../native-image';
import { trustedVerifiedActor } from '../../../verified-actor';
import { HttpClient } from '@angular/common/http';
import {
  Component,
  ChangeDetectorRef,
  DestroyRef,
  effect,
  inject,
  input,
  output,
  signal,
  viewChild,
} from '@angular/core';
import type { OnChanges, ElementRef } from '@angular/core';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { TuiAutoFocus, TuiPan } from '@taiga-ui/cdk';
import { TuiButton, TuiDialog, TuiLink, TuiLoader } from '@taiga-ui/core';
import {
  CancelledError,
  MutationObserver,
  QueryClient,
  QueryObserver,
  queryOptions,
  skipToken,
} from '@tanstack/angular-query-experimental';
import type {
  Query,
  QueryFunctionContext,
  QueryObserverResult,
} from '@tanstack/angular-query-experimental';
import type { Api } from '../../../../api.generated';
import { ApiFailure, readJson, writeJson } from '../../../../api-http';
import { isUncertain } from '../../../uncertain';
import { isPhotoUpload, isPhotoResume } from './photo-contract';
import {
  croppedImage,
  initialCrop,
  maxPhotoBytes,
  moveCrop,
  sourceHash,
  sourceType,
  zoomCrop,
} from './image';
import type { Crop } from './image';
import { transferPhoto } from './transfer';

interface StartIntent {
  readonly accountId: string;
  readonly body: Api['schemas']['StartPhotoRequest'];
  readonly key: string;
}
interface ActionIntent {
  readonly accountId: string;
  readonly uploadId: string;
  readonly key: string;
}
function resumeOptions(http: Readonly<HttpClient>, accountId: string | null, enabled: boolean) {
  return queryOptions({
    queryKey: ['account', accountId, 'photo-uploads'] as const,
    enabled,
    retry: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    queryFn: ({ signal }: Readonly<QueryFunctionContext>) =>
      readJson(http, '/api/v1/media/uploads', signal, isPhotoResume),
  });
}
function uploadOptions(
  http: Readonly<HttpClient>,
  accountId: string | null,
  id: string | null,
  enabled = true,
) {
  return queryOptions({
    queryKey: ['account', accountId, 'photo-upload', id] as const,
    enabled: id !== null && enabled,
    retry: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    refetchInterval: (query: Readonly<Query<Api['schemas']['PhotoUploadResponse']>>) =>
      enabled ? (query.state.data?.poll_after_ms ?? false) : false,
    queryFn:
      id === null
        ? skipToken
        : ({ signal }: Readonly<QueryFunctionContext>) =>
            readJson(http, `/api/v1/media/${encodeURIComponent(id)}`, signal, isPhotoUpload),
  });
}

@Component({
  selector: 'peerly-photo',
  imports: [
    NativeImage,
    ReactiveFormsModule,
    TuiAutoFocus,
    TuiPan,
    TuiButton,
    TuiDialog,
    TuiLink,
    TuiLoader,
  ],
  templateUrl: './photo.html',
  styleUrl: './photo.less',
})
export class PhotoWorkflow implements OnChanges {
  public readonly actor = input.required<Api['schemas']['IdentityResponse']>();
  public readonly checking = input(false);
  public readonly photoVersion = input.required<number>();
  public readonly currentPhoto = input.required<Api['schemas']['CurrentPhotoResponse'] | null>();
  public readonly refreshProfile = output();
  public readonly expired = output();
  private readonly http = inject(HttpClient);
  private readonly client = inject(QueryClient);
  private readonly change = inject(ChangeDetectorRef);
  private readonly destroy = inject(DestroyRef);
  private readonly lifetime = new AbortController();
  private readonly preview = viewChild<ElementRef<HTMLCanvasElement>>('preview');
  private readonly fileInput = viewChild.required<ElementRef<HTMLInputElement>>('fileInput');
  private readonly cameraInput = viewChild.required<ElementRef<HTMLInputElement>>('cameraInput');
  private readonly bitmap = signal<ImageBitmap | null>(null);
  private readonly transferAbort = signal<AbortController | null>(null);
  private readonly file = new FormControl<File | null>(null);
  private readonly selectionVersion = signal<number | null>(null);
  private readonly selected = new FormControl<Blob | null>(null);
  private readonly crop = new FormControl<Crop | null>(null);
  protected readonly editing = signal(false);
  protected readonly preparing = signal(false);
  protected readonly localError = signal<string | null>(null);
  protected readonly transferInterrupted = signal(false);
  protected readonly maxBytes = maxPhotoBytes;
  private readonly resumeQuery = new QueryObserver(
    this.client,
    resumeOptions(this.http, null, false),
  );
  private readonly uploadQuery = new QueryObserver(
    this.client,
    uploadOptions(this.http, null, null),
  );
  private readonly startMutation = new MutationObserver(this.client, {
    retry: false,
    mutationFn: (intent: Readonly<StartIntent>) => {
      const actor = this.authority(intent.accountId);
      return writeJson(
        this.http,
        '/api/v1/media/uploads',
        intent.body,
        { 'x-csrf-token': actor.csrf_token, 'idempotency-key': intent.key },
        (value): value is Api['schemas']['PhotoUploadResponse'] =>
          isPhotoUpload(value) &&
          value.content_type === intent.body.content_type &&
          value.size_bytes === intent.body.size_bytes &&
          value.expected_photo_version === intent.body.expected_photo_version,
      );
    },
    onSuccess: async (result, intent: Readonly<StartIntent>) => {
      if (!this.current(intent.accountId)) return;
      this.cacheUpload(result);
      this.uploadQuery.setOptions(
        uploadOptions(this.http, intent.accountId, result.id, this.permitted),
      );
      if (this.permitted)
        await Promise.all([
          this.uploadQuery.refetch({ cancelRefetch: false }),
          this.resumeQuery.refetch(),
        ]);
    },
    onError: (error: unknown, intent: Readonly<StartIntent>) => {
      if (this.current(intent.accountId)) this.denied(error);
    },
  });
  private readonly finalizeMutation = new MutationObserver(this.client, {
    retry: false,
    mutationFn: (intent: Readonly<ActionIntent>) => this.command(intent, 'finalize'),
    onSuccess: async (_result, intent: Readonly<ActionIntent>) => {
      if (this.current(intent.accountId)) {
        this.cacheUpload(_result);
        if (this.permitted)
          await Promise.all([this.uploadQuery.refetch(), this.resumeQuery.refetch()]);
      }
    },
    onError: (error: unknown, intent: Readonly<ActionIntent>) => {
      if (this.current(intent.accountId)) this.denied(error);
    },
  });
  private readonly cancelMutation = new MutationObserver(this.client, {
    retry: false,
    mutationFn: (intent: Readonly<ActionIntent>) => this.command(intent, 'cancel'),
    onSuccess: async (_result, intent: Readonly<ActionIntent>) => {
      if (this.current(intent.accountId)) {
        this.cacheUpload(_result);
        if (this.permitted)
          await Promise.all([this.uploadQuery.refetch(), this.resumeQuery.refetch()]);
      }
    },
    onError: (error: unknown, intent: Readonly<ActionIntent>) => {
      if (this.current(intent.accountId)) this.denied(error);
    },
  });
  protected get history() {
    return this.resumeQuery.getCurrentResult();
  }
  protected get reselecting(): boolean {
    const id = this.upload.data?.id;
    return (
      this.upload.data?.state === 'uploading' &&
      this.history.data?.uploads.some((item) => item.upload.id === id) === true
    );
  }
  protected get upload() {
    return this.uploadQuery.getCurrentResult();
  }
  protected get starting() {
    return this.startMutation.getCurrentResult();
  }
  protected get finalizing() {
    return this.finalizeMutation.getCurrentResult();
  }
  protected get cancelling() {
    return this.cancelMutation.getCurrentResult();
  }
  protected get displayPhoto(): Api['schemas']['CurrentPhotoResponse'] | null {
    const recent = this.history.data?.photo;
    return recent !== undefined && recent !== null && recent.version > this.photoVersion()
      ? recent
      : this.currentPhoto();
  }
  protected get completedSelection(): boolean {
    return this.upload.data !== undefined && !this.pending;
  }
  public get hasLocalDraft(): boolean {
    return (
      this.file.value !== null &&
      this.upload.data?.state !== 'ready' &&
      this.upload.data?.state !== 'queued' &&
      this.upload.data?.state !== 'processing'
    );
  }
  public get hasUnconfirmedAction(): boolean {
    return (
      this.starting.isPending ||
      this.finalizing.isPending ||
      this.cancelling.isPending ||
      this.transferAbort() !== null ||
      this.replayStart ||
      isUncertain(this.finalizing.error) ||
      isUncertain(this.cancelling.error)
    );
  }
  protected get hasSelectedFile(): boolean {
    return this.selected.value !== null;
  }
  protected get hasPreview(): boolean {
    return this.bitmap() !== null;
  }
  protected get permitted(): boolean {
    return (
      !this.checking() &&
      this.current(this.actor().account_id) &&
      trustedVerifiedActor(this.client, this.actor().account_id) !== null
    );
  }
  private authorized(accountId: string): boolean {
    return (
      !this.checking() &&
      this.current(accountId) &&
      trustedVerifiedActor(this.client, accountId) !== null
    );
  }
  private authority(accountId: string): Api['schemas']['IdentityResponse'] {
    const actor = trustedVerifiedActor(this.client, accountId);
    if (this.checking() || !this.current(accountId) || actor === null) throw new CancelledError();
    return actor;
  }
  protected get replayStart(): boolean {
    return isUncertain(this.starting.error) || this.starting.error instanceof CancelledError;
  }
  protected get nativeBusy(): boolean {
    return !this.permitted || this.preparing() || this.transferAbort() !== null;
  }
  protected get busy(): boolean {
    return (
      this.nativeBusy ||
      this.starting.isPending ||
      this.finalizing.isPending ||
      this.cancelling.isPending
    );
  }
  protected get pending(): boolean {
    return (
      this.upload.data !== undefined &&
      ['uploading', 'queued', 'processing'].includes(this.upload.data.state)
    );
  }
  protected get locked(): boolean {
    return (
      this.busy ||
      !this.history.isSuccess ||
      (this.upload.isFetching && this.upload.data === undefined) ||
      (this.pending && !this.reselecting) ||
      this.replayStart
    );
  }
  protected get photoConflict(): boolean {
    return (
      this.starting.error instanceof ApiFailure &&
      this.starting.error.code === 'photo_version_conflict'
    );
  }
  protected get rejectionMessage(): string {
    switch (this.upload.data?.failure) {
      case 'storage_unavailable':
        return 'Photo storage is temporarily unavailable. This upload wasn’t saved. You can try uploading the same photo again later.';
      case 'processing_unavailable':
        return 'Photo processing is temporarily unavailable. This upload wasn’t saved. You can try uploading the same photo again later.';
      default:
        return 'We couldn’t use this photo. Choose another JPEG or PNG, or try again if processing was unavailable.';
    }
  }
  protected async reloadPhoto(): Promise<void> {
    if (!this.permitted) return;
    if (this.busy || !this.photoConflict) return;
    const accountId = this.actor().account_id;
    await this.resumeQuery.refetch();
    if (this.current(accountId) && this.history.isSuccess) {
      this.selectionVersion.set(this.history.data.photo?.version ?? 0);
      this.startMutation.reset();
      this.refreshProfile.emit();
    }
  }
  protected get problem(): string | null {
    if (this.localError() !== null) return this.localError();
    if (this.starting.error instanceof CancelledError)
      return 'The photo request paused during a sign-in check. Retry the same request when sign-in is confirmed.';
    if (this.replayStart)
      return 'We couldn’t confirm the photo request. Retry the same request to find its outcome.';
    if (isUncertain(this.finalizing.error))
      return 'We couldn’t confirm processing started. Check status before retrying finalization.';
    if (isUncertain(this.cancelling.error))
      return 'We couldn’t confirm cancellation. Check status before retrying the same cancellation.';
    if (this.photoConflict)
      return 'Your photo changed elsewhere. Reload your profile before starting another upload.';
    if (this.starting.isError || this.finalizing.isError || this.cancelling.isError)
      return 'The photo action couldn’t be completed. Check status or try again explicitly.';
    return null;
  }
  public constructor() {
    effect(() => {
      this.preview();
      this.bitmap();
      this.draw();
    });
    const stopCrop = this.crop.valueChanges.subscribe(() => {
      this.draw();
    });
    const update = () => {
      this.change.markForCheck();
    };
    const stopQuery = this.uploadQuery.subscribe(
      (result: Readonly<QueryObserverResult<Api['schemas']['PhotoUploadResponse']>>) => {
        this.denied(result.error);
        if (result.isSuccess && !result.isFetching && result.data.state === 'ready') {
          if (this.permitted) void this.resumeQuery.refetch();
          this.refreshProfile.emit();
        }
        update();
      },
    );
    const stopHistory = this.resumeQuery.subscribe(
      (result: Readonly<QueryObserverResult<Api['schemas']['OwnPhotoResumeResponse']>>) => {
        this.denied(result.error);
        update();
      },
    );
    const stopStart = this.startMutation.subscribe(update);
    const stopFinalize = this.finalizeMutation.subscribe(update);
    const stopCancel = this.cancelMutation.subscribe(update);
    this.destroy.onDestroy(() => {
      this.lifetime.abort();
      this.clear();
      stopCrop.unsubscribe();
      stopQuery();
      stopHistory();
      this.resumeQuery.destroy();
      stopStart();
      stopFinalize();
      stopCancel();
      this.uploadQuery.destroy();
    });
  }
  public ngOnChanges(): void {
    const sameOwner = this.uploadQuery.options.queryKey[1] === this.actor().account_id;
    const selected = this.uploadQuery.options.queryKey[3];
    if (sameOwner && selected !== null && typeof selected !== 'string')
      throw new Error('Invalid photo query identity');
    const id = sameOwner && typeof selected === 'string' ? selected : null;
    if (!sameOwner) {
      this.clear();
      this.startMutation.reset();
      this.finalizeMutation.reset();
      this.cancelMutation.reset();
    }
    if (!this.permitted) this.transferAbort()?.abort();
    this.uploadQuery.setOptions(
      uploadOptions(this.http, this.actor().account_id, id, this.permitted),
    );
    this.resumeQuery.setOptions(resumeOptions(this.http, this.actor().account_id, this.permitted));
  }
  private current(accountId: string): boolean {
    const actor = this.client.getQueryData<Api['schemas']['IdentityResponse'] | null>(['session']);
    return (
      !this.lifetime.signal.aborted &&
      this.actor().account_id === accountId &&
      actor?.account_id === accountId
    );
  }
  private clear(): void {
    this.transferAbort()?.abort();
    this.transferAbort.set(null);
    this.bitmap()?.close();
    this.bitmap.set(null);
    this.file.reset(null, { emitEvent: false });
    this.selected.reset();
    this.selectionVersion.set(null);
    this.crop.reset();
    this.editing.set(false);
    this.preparing.set(false);
    this.localError.set(null);
    this.transferInterrupted.set(false);
  }
  private denied(error: unknown): void {
    if (
      this.current(this.actor().account_id) &&
      error instanceof ApiFailure &&
      (error.status === 401 || error.status === 403)
    ) {
      this.clear();
      this.client.removeQueries({ queryKey: ['account', this.actor().account_id] });
      this.expired.emit();
    }
  }
  private cacheUpload(result: Api['schemas']['PhotoUploadResponse']): void {
    const key = ['account', this.actor().account_id, 'photo-upload', result.id] as const;
    const previous = this.client.getQueryData<Api['schemas']['PhotoUploadResponse']>(key);
    if (previous === undefined || result.version > previous.version)
      this.client.setQueryData(key, result);
  }
  private command(
    intent: Readonly<ActionIntent>,
    action: 'finalize' | 'cancel',
  ): Promise<Api['schemas']['PhotoUploadResponse']> {
    const actor = this.authority(intent.accountId);
    return writeJson(
      this.http,
      `/api/v1/media/uploads/${encodeURIComponent(intent.uploadId)}/${action}`,
      undefined,
      { 'x-csrf-token': actor.csrf_token, 'idempotency-key': intent.key },
      (value): value is Api['schemas']['PhotoUploadResponse'] =>
        isPhotoUpload(value) && value.id === intent.uploadId,
    );
  }
  private newDraft(): void {
    this.startMutation.reset();
    this.finalizeMutation.reset();
    this.cancelMutation.reset();
    this.localError.set(null);
    this.transferInterrupted.set(false);
    this.uploadQuery.setOptions(uploadOptions(this.http, this.actor().account_id, null));
  }
  protected chooseFile(): void {
    if (this.locked) return;
    if (this.completedSelection) this.newDraft();
    this.fileInput().nativeElement.click();
  }
  protected takePhoto(): void {
    if (this.locked) return;
    if (this.completedSelection) this.newDraft();
    this.cameraInput().nativeElement.click();
  }
  protected picked(event: Readonly<Event>): void {
    if (this.locked || !(event.target instanceof HTMLInputElement)) return;
    const file = event.target.files?.item(0);
    if (file !== undefined && file !== null) {
      this.selectionVersion.set(
        Math.max(this.history.data?.photo?.version ?? 0, this.photoVersion()),
      );
      this.file.setValue(file);
      void this.prepare(file);
    }
  }
  protected review(): void {
    if (this.locked || this.bitmap() === null) return;
    if (this.completedSelection) this.newDraft();
    this.editing.set(true);
  }
  protected reject(): void {
    this.localError.set('Choose a JPEG or PNG photo, up to 10 MB.');
  }
  private async prepare(file: Readonly<File>): Promise<void> {
    const accountId = this.actor().account_id;
    this.localError.set(null);
    this.bitmap()?.close();
    this.bitmap.set(null);
    this.crop.reset();
    this.selected.reset();
    this.editing.set(false);
    this.preparing.set(true);
    try {
      if ((await sourceType(file)) === null) {
        if (this.current(accountId) && this.file.value === file) this.reject();
        return;
      }
      const bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' });
      if (!this.current(accountId) || this.file.value !== file) {
        bitmap.close();
        return;
      }
      this.bitmap()?.close();
      this.bitmap.set(bitmap);
      this.crop.reset(initialCrop(bitmap));
      this.selected.reset();
      this.editing.set(true);
      if (this.uploadQuery.options.queryKey[3] === null) this.newDraft();
    } catch (error: unknown) {
      if (error instanceof DOMException || error instanceof TypeError) {
        if (this.current(accountId)) this.reject();
      } else throw error;
    } finally {
      if (this.current(accountId)) this.preparing.set(false);
    }
  }
  private draw(): void {
    const canvas = this.preview()?.nativeElement;
    const bitmap = this.bitmap();
    const crop = this.crop.value;
    if (canvas === undefined || bitmap === null || crop === null) return;
    canvas
      .getContext('2d')
      ?.drawImage(
        bitmap,
        crop.left,
        crop.top,
        crop.edge,
        crop.edge,
        0,
        0,
        canvas.width,
        canvas.height,
      );
  }
  protected pan(delta: readonly [number, number]): void {
    const width = this.preview()?.nativeElement.getBoundingClientRect().width;
    const crop = this.crop.value;
    if (width !== undefined && width > 0 && crop !== null)
      this.move((-delta[0] * crop.edge) / width, (-delta[1] * crop.edge) / width);
  }
  protected move(x: number, y: number): void {
    const bitmap = this.bitmap();
    const crop = this.crop.value;
    if (bitmap !== null && crop !== null) this.crop.setValue(moveCrop(crop, bitmap, x, y));
  }
  protected zoom(ratio: number): void {
    const bitmap = this.bitmap();
    const crop = this.crop.value;
    if (bitmap !== null && crop !== null) this.crop.setValue(zoomCrop(crop, bitmap, ratio));
  }
  protected resetCrop(): void {
    const bitmap = this.bitmap();
    if (bitmap !== null) this.crop.setValue(initialCrop(bitmap));
  }
  protected key(event: Readonly<KeyboardEvent>): void {
    if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', '+', '=', '-', '0'].includes(event.key))
      event.preventDefault();
    switch (event.key) {
      case 'ArrowLeft':
        this.move(-8, 0);
        break;
      case 'ArrowRight':
        this.move(8, 0);
        break;
      case 'ArrowUp':
        this.move(0, -8);
        break;
      case 'ArrowDown':
        this.move(0, 8);
        break;
      case '+':
      case '=':
        this.zoom(1.25);
        break;
      case '-':
        this.zoom(0.8);
        break;
      case '0':
        this.resetCrop();
    }
  }
  protected async usePhoto(original: boolean): Promise<void> {
    const bitmap = this.bitmap();
    const crop = this.crop.value;
    const file = this.file.value;
    if (this.busy || bitmap === null || crop === null || file === null) return;
    const accountId = this.actor().account_id;
    this.preparing.set(true);
    try {
      const selected = original ? file : await croppedImage(bitmap, crop);
      if (!this.current(accountId)) return;
      this.selected.setValue(selected);
      this.editing.set(false);
    } catch (error: unknown) {
      if (!(error instanceof DOMException)) throw error;
      if (this.current(accountId))
        this.localError.set('We couldn’t prepare this file. Reselect your photo and try again.');
      return;
    } finally {
      if (this.current(accountId)) this.preparing.set(false);
    }
    if (this.current(accountId) && this.permitted) await this.send();
  }
  protected async send(): Promise<void> {
    const file = this.selected.value;
    if (file === null || this.busy) return;
    const known = this.upload.data;
    if (known !== undefined && known.state !== 'uploading') {
      this.localError.set(
        'This upload has already moved on. Check its status before starting another photo.',
      );
      return;
    }
    if (!this.history.isSuccess || this.history.isFetching) return;
    const accountId = this.actor().account_id;
    const version =
      this.selectionVersion() ??
      Math.max(this.history.data.photo?.version ?? 0, this.photoVersion());
    this.localError.set(null);
    this.preparing.set(true);
    try {
      const contentType = await sourceType(file);
      if (contentType === null) {
        this.reject();
        return;
      }
      const sha = await sourceHash(file);
      if (!this.current(accountId) || !this.permitted) return;
      this.preparing.set(false);
      const current = this.upload.data;
      if (current?.state === 'uploading') {
        const original = this.resumeQuery
          .getCurrentResult()
          .data?.uploads.find((item) => item.upload.id === current.id);
        const hash = original?.source_sha256 ?? this.starting.variables?.body.sha256;
        if (
          hash !== sha ||
          current.size_bytes !== file.size ||
          current.content_type !== contentType
        ) {
          this.localError.set(
            'This file does not match that upload. Reselect the exact file, or cancel the previous upload before starting a new request.',
          );
          return;
        }
        await this.sendBytes(current.id, file, accountId);
        return;
      }
      if (current !== undefined) {
        this.localError.set(
          'This upload has already moved on. Check its status before starting another photo.',
        );
        return;
      }
      const intent = {
        accountId,
        key: crypto.randomUUID(),
        body: {
          size_bytes: file.size,
          sha256: sha,
          content_type: contentType,
          expected_photo_version: version,
        },
      };
      await this.startMutation.mutate(intent);
      const updated = this.uploadQuery.getCurrentResult().data;
      if (!this.current(accountId) || updated?.state !== 'uploading') return;
      if (!this.authorized(accountId)) {
        this.pauseTransfer();
        return;
      }
      await this.sendBytes(updated.id, file, accountId);
    } catch (error: unknown) {
      if (!this.current(accountId)) return;
      if (error instanceof ApiFailure) {
        this.denied(error);
        if (
          !this.starting.isError &&
          !this.finalizing.isError &&
          error.status !== 401 &&
          error.status !== 403
        )
          this.localError.set(
            error.code === 'photo_transfer_unknown' || error.code === 'photo_transfer_failed'
              ? 'We couldn’t confirm the file transfer. Check status before retrying the original file.'
              : 'We couldn’t access this upload. Check status before retrying the original file.',
          );
      } else if (error instanceof CancelledError) {
        return;
      } else if (error instanceof DOMException) {
        if (error.name === 'AbortError') this.pauseTransfer();
        else this.localError.set('We couldn’t read this file. Reselect your photo and try again.');
      } else throw error;
    } finally {
      if (this.current(accountId)) this.preparing.set(false);
    }
  }
  protected async retryStart(): Promise<void> {
    if (this.busy) return;
    const previous = this.starting.variables;
    if (!this.replayStart || previous === undefined) {
      await this.send();
      return;
    }
    try {
      // Resolve the immutable creation intent even when the local file is no longer readable.
      // Byte reuse is checked separately against the recovered owner projection in send().
      await this.startMutation.mutate(previous);
      const updated = this.uploadQuery.getCurrentResult().data;
      if (this.current(previous.accountId) && updated?.state === 'uploading') await this.send();
    } catch (error: unknown) {
      if (!(error instanceof ApiFailure) && !(error instanceof CancelledError)) throw error;
    }
  }
  protected async refreshHistory(): Promise<void> {
    if (!this.permitted) return;
    await this.resumeQuery.refetch();
  }
  protected async resumeUpload(id: string): Promise<void> {
    if (this.busy || this.history.data?.uploads.some((item) => item.upload.id === id) !== true)
      return;
    this.clear();
    this.startMutation.reset();
    this.finalizeMutation.reset();
    this.cancelMutation.reset();
    this.uploadQuery.setOptions(uploadOptions(this.http, this.actor().account_id, id));
    await this.uploadQuery.refetch();
  }
  protected async checkStatus(): Promise<void> {
    if (!this.permitted) return;
    await this.uploadQuery.refetch();
  }
  protected async cancel(): Promise<void> {
    const current = this.upload.data;
    if (!this.permitted || this.cancelling.isPending || current === undefined) return;
    this.transferAbort()?.abort();
    const previous = this.cancelling.variables;
    const intent =
      isUncertain(this.cancelling.error) && previous !== undefined
        ? previous
        : {
            accountId: this.actor().account_id,
            uploadId: current.id,
            key: crypto.randomUUID(),
          };
    try {
      await this.cancelMutation.mutate(intent);
    } catch (error: unknown) {
      if (!(error instanceof ApiFailure) && !(error instanceof CancelledError)) throw error;
    }
  }
  protected async retryFinalize(): Promise<void> {
    const previous = this.finalizing.variables;
    if (this.busy || previous === undefined) return;
    try {
      await this.finalizeMutation.mutate(previous);
    } catch (error: unknown) {
      if (!(error instanceof ApiFailure) && !(error instanceof CancelledError)) throw error;
    }
  }
  private async sendBytes(
    uploadId: string,
    file: Readonly<Blob>,
    accountId: string,
  ): Promise<void> {
    const controller = new AbortController();
    this.transferAbort.set(controller);
    const stop = () => {
      controller.abort();
    };
    this.lifetime.signal.addEventListener('abort', stop, { once: true });
    try {
      const actor = this.authority(accountId);
      this.transferInterrupted.set(false);
      await transferPhoto(
        this.http,
        uploadId,
        actor.csrf_token,
        file,
        controller.signal,
        () => this.permitted && this.current(accountId),
      );
    } finally {
      this.lifetime.signal.removeEventListener('abort', stop);
      if (this.transferAbort() === controller) this.transferAbort.set(null);
    }
    if (!this.current(accountId)) return;
    if (!this.permitted || controller.signal.aborted) {
      this.pauseTransfer();
      return;
    }
    const previous = this.finalizing.variables;
    const intent =
      isUncertain(this.finalizing.error) && previous !== undefined
        ? previous
        : { accountId, uploadId, key: crypto.randomUUID() };
    await this.finalizeMutation.mutate(intent);
  }
  private pauseTransfer(): void {
    const accountId = this.actor().account_id;
    const key = this.uploadQuery.options.queryKey;
    if (
      this.current(accountId) &&
      key[1] === accountId &&
      typeof key[3] === 'string' &&
      (this.upload.data === undefined || this.upload.data.state === 'uploading') &&
      this.selected.value !== null &&
      !this.cancelling.isPending
    )
      this.transferInterrupted.set(true);
  }
  protected async retryTransfer(): Promise<void> {
    if (this.upload.data?.state === 'uploading') await this.send();
  }
}
