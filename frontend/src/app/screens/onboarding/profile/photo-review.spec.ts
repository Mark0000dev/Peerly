import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { QueryClient } from '@tanstack/angular-query-experimental';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { verifiedActor } from '../onboarding.fixtures';
import { PhotoReview } from './photo-review';

describe('owner photo recovery projection', () => {
  let fixture: ComponentFixture<PhotoReview>;
  let backend: HttpTestingController;
  let client: QueryClient;
  beforeEach(() => {
    TestBed.resetTestingModule();
    client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    client.setQueryData(['session'], verifiedActor);
    TestBed.configureTestingModule({
      imports: [PhotoReview],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: QueryClient, useValue: client },
      ],
    });
    fixture = TestBed.createComponent(PhotoReview);
    backend = TestBed.inject(HttpTestingController);
    fixture.componentRef.setInput('actor', verifiedActor);
    fixture.detectChanges();
  });
  afterEach(() => {
    fixture.destroy();
    client.clear();
    backend.verify();
  });
  function text(): string {
    const element: unknown = fixture.nativeElement;
    if (!(element instanceof HTMLElement)) throw new Error('Missing view');
    return element.textContent;
  }
  async function shown(value: string): Promise<void> {
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(text()).toContain(value);
    });
  }
  it('retains human restriction after replacement upload and only reads explicit status', async () => {
    backend
      .expectOne('/api/v1/me/photo-review')
      .flush({ version: 1, state: 'replacement_required' });
    await shown('A different profile photo is needed');
    const element: unknown = fixture.nativeElement;
    if (!(element instanceof HTMLElement)) throw new Error('Missing view');
    const button = element.querySelector('button');
    if (button === null) throw new Error('Missing explicit review action');
    button.click();
    backend
      .expectOne('/api/v1/me/photo-review')
      .flush({ version: 1, state: 'awaiting_human_review' });
    await shown('Your replacement is awaiting review');
    expect(text()).not.toContain('approved');
    backend.expectNone((request) => request.method !== 'GET');
  });
  it('does not describe a missing review as approval', async () => {
    backend.expectOne('/api/v1/me/photo-review').flush({ version: 0, state: 'not_required' });
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(text().trim()).toBe('');
    });
  });
  it('does not turn an unknown network result into approval', async () => {
    backend.expectOne('/api/v1/me/photo-review').error(new ProgressEvent('error'));
    await shown('This does not confirm approval.');
  });
  it('pauses during sign-in checking and cannot show an old actor recovery', () => {
    const pending = backend.expectOne('/api/v1/me/photo-review');
    fixture.componentRef.setInput('checking', true);
    fixture.detectChanges();
    expect(pending.cancelled).toBe(true);
    fixture.componentRef.setInput('actor', {
      ...verifiedActor,
      account_id: '00000000-0000-0000-0000-000000000003',
    });
    fixture.componentRef.setInput('checking', false);
    fixture.detectChanges();
    expect(text()).not.toContain('replacement');
    backend.expectNone('/api/v1/me/photo-review');
  });
});
