import { Component, input, output } from '@angular/core';
import { TuiRoot } from '@taiga-ui/core';
import type { Api } from '../../../api.generated';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { QueryClient, provideTanStackQuery } from '@tanstack/angular-query-experimental';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { appConfig } from '../../../app.config';
import { ProfileBasics, validateProfileLanguages } from './profile';
import { ownProfile, profileReference, revision } from './profile.fixtures';
import { verifiedActor } from '../onboarding.fixtures';
import { host, shown, control, submit, click } from '../testing-host';

const actor = {
  ...verifiedActor,
  capabilities: { ...verifiedActor.capabilities, can_use_student_features: true },
} as const;

@Component({
  imports: [ProfileBasics, TuiRoot],
  template: `<tui-root
    ><peerly-profile-basics [actor]="actor()" (expired)="expired.emit()"
  /></tui-root>`,
})
class ProfileDetailsHost {
  public readonly actor = input.required<Api['schemas']['IdentityResponse']>();
  public readonly expired = output();
}

describe('profile language input validation', () => {
  for (const choices of [['en', 'en'], ['unknown'], ['en', 'ms', 'zh', 'ta', 'ar', 'ru']]) {
    it(`rejects malformed selection ${choices.join(',')} before any request`, () => {
      expect(validateProfileLanguages(choices, profileReference)).toEqual({ languages: true });
    });
  }
  it('accepts an empty optional selection and only actual supported codes', () => {
    expect(validateProfileLanguages([], profileReference)).toBeNull();
    expect(validateProfileLanguages(['en', 'ms'], profileReference)).toBeNull();
  });
});

describe('explicit optional profile editor', () => {
  let fixture: ComponentFixture<ProfileDetailsHost>;
  let backend: HttpTestingController;
  let client: QueryClient;
  beforeEach(() => {
    TestBed.resetTestingModule();
    client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    client.setQueryData(['session'], actor);
    TestBed.configureTestingModule({
      providers: [...appConfig.providers, provideHttpClientTesting(), provideTanStackQuery(client)],
    });
    fixture = TestBed.createComponent(ProfileDetailsHost);
    fixture.componentRef.setInput('actor', actor);
    backend = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
  });
  afterEach(() => {
    try {
      fixture.destroy();
      client.clear();
      backend.verify();
    } finally {
      TestBed.resetTestingModule();
    }
  });
  async function load(): Promise<void> {
    const read = await vi.waitFor(() => backend.expectOne('/api/v1/me/profile'));
    read.flush(ownProfile);
    await shown(fixture, 'Edit profile');
    const summary = await vi.waitFor(() => backend.expectOne('/api/v1/me/feedback-summary'));
    summary.flush({ state: 'building', responses: 0, publicly_visible: true });
  }
  async function open(): Promise<void> {
    click(fixture, 'Edit profile');
    await shown(fixture, 'Loading language choices');
    const request = await vi.waitFor(() => backend.expectOne('/api/v1/profile-reference-data'));
    request.flush(profileReference);
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(host(fixture).textContent).not.toContain('Loading language choices');
      const picker = host(fixture).querySelector('#profile-languages');
      if (!(picker instanceof HTMLInputElement)) throw new Error('Missing languages input');
      expect(picker.readOnly).toBe(false);
    });
  }
  async function toggleLanguage(label: string): Promise<void> {
    const picker = host(fixture).querySelector('#profile-languages');
    if (!(picker instanceof HTMLInputElement)) throw new Error('Missing languages input');
    picker.focus();
    picker.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
    fixture.detectChanges();
    const option = await vi.waitFor(() => {
      const value = Array.from(document.querySelectorAll('[role="option"]')).find(
        (item: Readonly<Element>) => item.textContent.trim() === label,
      );
      if (!(value instanceof HTMLButtonElement)) throw new Error('Missing language option');
      return value;
    });
    option.click();
    fixture.detectChanges();
  }
  async function selectMalay(): Promise<void> {
    await toggleLanguage('English');
    await vi.waitFor(() => {
      expect(control(fixture, '#profile-languages').value).toEqual([]);
    });
    await toggleLanguage('Malay');
    await vi.waitFor(() => {
      expect(control(fixture, '#profile-languages').value).toEqual(['ms']);
    });
  }
  function edit(selector: string, value: unknown): void {
    control(fixture, selector).setValue(value);
    control(fixture, selector).markAsDirty();
  }
  it('keeps optional fields and reference requests out of setup until explicit editing', async () => {
    await load();
    expect(host(fixture).querySelector('#profile-about')).toBeNull();
    backend.expectNone('/api/v1/profile-reference-data');
    await open();
    expect(control(fixture, '#profile-about').value).toBe(revision.about);
    expect(control(fixture, '#profile-programme').value).toBe(revision.programme);
    expect(control(fixture, '#profile-year').value).toBe(revision.year_label);
    expect(control(fixture, '#profile-languages').value).toEqual(revision.languages);
    backend.expectNone((request) => request.method !== 'GET');
    fixture.componentRef.setInput('actor', verifiedActor);
    fixture.detectChanges();
    expect(host(fixture).textContent).not.toContain('Edit profile');
  });
  it('saves actual editable fields, language codes and the original CAS revision', async () => {
    await load();
    await open();
    edit('#profile-about', '  I enjoy working through examples.  ');
    edit('#profile-programme', 'Information Technology');
    edit('#profile-year', 'Year 2');
    edit('#profile-languages', ['en', 'ms']);
    submit(fixture);
    const request = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/me/profile', method: 'PUT' }),
    );
    expect(request.request.body).toEqual({
      about: 'I enjoy working through examples.',
      programme: 'Information Technology',
      year_label: 'Year 2',
      languages: ['en', 'ms'],
      task: 'find_help',
      display_name: revision.display_name,
      expected_version: 2,
    });
    expect(request.request.headers.get('x-csrf-token')).toBe(actor.csrf_token);
    expect(request.request.headers.get('idempotency-key')).toMatch(/^[a-f0-9-]{36}$/);
    const saved = {
      ...revision,
      about: 'I enjoy working through examples.',
      programme: 'Information Technology',
      year_label: 'Year 2',
      languages: ['en', 'ms'],
      version: 3,
    } as const;
    request.flush(saved);
    const refresh = await vi.waitFor(() => backend.expectOne('/api/v1/me/profile'));
    refresh.flush({ profile: saved, photo: null });
    await shown(fixture, 'Profile saved.');
    expect(control(fixture, '#profile-about').value).toBe(saved.about);
  });
  for (const [selector, limit] of [
    ['#profile-about', 160],
    ['#profile-programme', 80],
    ['#profile-year', 32],
  ] as const) {
    it(`validates ${selector} by Unicode code points and allows clearing it`, async () => {
      await load();
      await open();
      edit(selector, '😀'.repeat(limit));
      expect(control(fixture, selector).valid).toBe(true);
      edit(selector, 'a'.repeat(limit + 1));
      submit(fixture);
      await shown(fixture, 'Keep');
      backend.expectNone((request) => request.method === 'PUT');
      edit(selector, '  ');
      expect(control(fixture, selector).valid).toBe(true);
      submit(fixture);
      const request = await vi.waitFor(() =>
        backend.expectOne({ url: '/api/v1/me/profile', method: 'PUT' }),
      );
      const key =
        selector === '#profile-about'
          ? 'about'
          : selector === '#profile-programme'
            ? 'programme'
            : 'year_label';
      expect(request.request.body).toEqual(expect.objectContaining({ [key]: null }));
      request.flush({ code: 'invalid_profile' }, { status: 422, statusText: 'Invalid' });
      await shown(fixture, 'We couldn’t save your profile');
    });
  }
  for (const choices of [['en', 'ms', 'zh', 'ta', 'ar', 'ru']]) {
    it(`rejects unsupported, duplicated or excessive language selections ${choices.join(',')}`, async () => {
      await load();
      await open();
      edit('#profile-languages', choices);
      submit(fixture);
      await shown(fixture, 'Choose distinct languages');
      backend.expectNone((request) => request.method === 'PUT');
    });
  }
  it('retains all local draft fields while references fail and retries only explicitly', async () => {
    await load();
    click(fixture, 'Edit profile');
    await shown(fixture, 'Loading language choices');
    edit('#profile-about', 'Draft still here');
    const request = await vi.waitFor(() => backend.expectOne('/api/v1/profile-reference-data'));
    request.flush({ code: 'unavailable' }, { status: 503, statusText: 'Unavailable' });
    await shown(fixture, 'We couldn’t load language choices');
    submit(fixture);
    backend.expectNone((request) => request.method === 'PUT');
    expect(control(fixture, '#profile-about').value).toBe('Draft still here');
    click(fixture, 'Retry language choices');
    const retry = await vi.waitFor(() => backend.expectOne('/api/v1/profile-reference-data'));
    retry.flush(profileReference);
    await shown(fixture, 'Choose up to 5 languages');
    expect(control(fixture, '#profile-about').value).toBe('Draft still here');
    click(fixture, 'Cancel changes');
    await shown(fixture, 'Discard unsaved changes?');
    click(fixture, 'Discard changes');
    await shown(fixture, 'Edit profile');
    (await vi.waitFor(() => backend.expectOne('/api/v1/me/feedback-summary'))).flush({
      state: 'building',
      responses: 0,
      publicly_visible: true,
    });
    click(fixture, 'Edit profile');
    await shown(fixture, 'About · optional');
    expect(control(fixture, '#profile-about').value).toBe(revision.about);
    backend.expectNone('/api/v1/profile-reference-data');
  });
  it('same actor replacement metadata preserves drafts; Cancel restores the actual saved fields', async () => {
    await load();
    await open();
    edit('#profile-name', 'Different draft');
    edit('#profile-about', 'Private unsaved draft');
    edit('#profile-programme', 'New programme');
    edit('#profile-year', 'Year 3');
    await selectMalay();
    client.setQueryData(['session'], { ...actor, csrf_token: 'fresh-csrf' });
    fixture.componentRef.setInput('actor', { ...actor, csrf_token: 'fresh-csrf' });
    fixture.detectChanges();
    expect(control(fixture, '#profile-about').value).toBe('Private unsaved draft');
    click(fixture, 'Cancel changes');
    await shown(fixture, 'Discard unsaved changes?');
    click(fixture, 'Discard changes');
    await shown(fixture, 'Edit profile');
    (await vi.waitFor(() => backend.expectOne('/api/v1/me/feedback-summary'))).flush({
      state: 'building',
      responses: 0,
      publicly_visible: true,
    });
    expect(control(fixture).value).toBe(revision.display_name);
    click(fixture, 'Edit profile');
    await shown(fixture, 'About · optional');
    expect(control(fixture, '#profile-about').value).toBe(revision.about);
    expect(control(fixture, '#profile-programme').value).toBe(revision.programme);
    expect(control(fixture, '#profile-year').value).toBe(revision.year_label);
    expect(control(fixture, '#profile-languages').value).toEqual(revision.languages);
    backend.expectNone((request) => request.method === 'PUT');
  });
  it('unknown save keeps all fields locked and explicitly replays the immutable original CAS intent', async () => {
    await load();
    await open();
    edit('#profile-about', 'Uncertain draft');
    edit('#profile-programme', 'Computing science');
    edit('#profile-year', 'Year 3');
    await selectMalay();
    submit(fixture);
    const first = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/me/profile', method: 'PUT' }),
    );
    const body: unknown = first.request.body;
    const key = first.request.headers.get('idempotency-key');
    first.error(new ProgressEvent('error'));
    await shown(fixture, 'We couldn’t confirm your save');
    const field = host(fixture).querySelector('#profile-about');
    expect(field).toBeInstanceOf(HTMLTextAreaElement);
    if (!(field instanceof HTMLTextAreaElement)) throw new Error('Missing textarea');
    expect(field.readOnly).toBe(true);
    const cancel = Array.from(host(fixture).querySelectorAll('button')).find(
      (button: Readonly<HTMLButtonElement>) => button.textContent.trim() === 'Cancel changes',
    );
    expect(cancel?.disabled).toBe(true);
    client.setQueryData(['account', actor.account_id, 'profile'], {
      ...ownProfile,
      profile: { ...revision, version: 9 },
    });
    client.setQueryData(['session'], { ...actor, csrf_token: 'rotated-csrf' });
    fixture.componentRef.setInput('actor', { ...actor, csrf_token: 'rotated-csrf' });
    fixture.detectChanges();
    expect(control(fixture, '#profile-about').value).toBe('Uncertain draft');
    submit(fixture);
    const replay = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/me/profile', method: 'PUT' }),
    );
    expect(replay.request.body).toEqual(body);
    expect(replay.request.headers.get('idempotency-key')).toBe(key);
    expect(replay.request.headers.get('x-csrf-token')).toBe('rotated-csrf');
    replay.flush({ code: 'profile_version_conflict' }, { status: 409, statusText: 'Conflict' });
    await shown(fixture, 'Your profile changed elsewhere');
    expect(control(fixture, '#profile-year').value).toBe('Year 3');
  });
  for (const status of [401, 403])
    it(`reference ${String(status)} retires private optional drafts`, async () => {
      const expired = vi.fn();
      fixture.componentInstance.expired.subscribe(expired);
      await load();
      click(fixture, 'Edit profile');
      await shown(fixture, 'Loading language choices');
      edit('#profile-about', 'Sensitive draft');
      edit('#profile-programme', 'Unsent programme');
      const request = await vi.waitFor(() => backend.expectOne('/api/v1/profile-reference-data'));
      request.flush({ code: 'unavailable' }, { status, statusText: 'Unavailable' });
      await shown(fixture, 'We couldn’t load language choices');
      expect(expired).toHaveBeenCalledOnce();
      expect(control(fixture, '#profile-about').value).toBe('');
      expect(control(fixture, '#profile-programme').value).toBe('');
    });
  it('uses public multi-select CVA to select known codes through the actual dropdown', async () => {
    await load();
    await open();
    const picker = host(fixture).querySelector('#profile-languages');
    if (!(picker instanceof HTMLInputElement)) throw new Error('Missing languages input');
    picker.focus();
    picker.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
    fixture.detectChanges();
    const option = await vi.waitFor(() => {
      const value = Array.from(document.querySelectorAll('[role="option"]')).find(
        (item: Readonly<Element>) => item.textContent.trim() === 'Malay',
      );
      expect(value).toBeInstanceOf(HTMLButtonElement);
      if (!(value instanceof HTMLButtonElement)) throw new Error('Missing Malay option');
      return value;
    });
    option.click();
    fixture.detectChanges();
    await vi.waitFor(() => {
      expect(control(fixture, '#profile-languages').value).toEqual(['en', 'ms']);
    });
    expect(control(fixture, '#profile-languages').dirty).toBe(true);
    edit('#profile-about', 'Keep the language picker stable');
    fixture.detectChanges();
    expect(
      Array.from(document.querySelectorAll('[role="option"]')).find(
        (item: Readonly<Element>) => item.textContent.trim() === 'Malay',
      ),
    ).toBe(option);
    picker.blur();
    fixture.detectChanges();
    await vi.waitFor(() => {
      expect(control(fixture, '#profile-languages').touched).toBe(true);
    });
    expect(revision.languages).toEqual(['en']);
    backend.expectNone((request) => request.method === 'PUT');
  });
  it('keeps all fields after an unknown conflict and requires explicit canonical reload', async () => {
    await load();
    await open();
    edit('#profile-about', 'Unsent conflict draft');
    submit(fixture);
    const save = await vi.waitFor(() =>
      backend.expectOne({ url: '/api/v1/me/profile', method: 'PUT' }),
    );
    save.flush({ code: 'other_conflict' }, { status: 409, statusText: 'Conflict' });
    await shown(fixture, 'We couldn’t resolve this save');
    expect(control(fixture, '#profile-about').value).toBe('Unsent conflict draft');
    submit(fixture);
    backend.expectNone((request) => request.method === 'PUT');
    click(fixture, 'Reload saved profile');
    const read = await vi.waitFor(() => backend.expectOne('/api/v1/me/profile'));
    read.flush(ownProfile);
    await shown(fixture, 'Edit profile');
    (await vi.waitFor(() => backend.expectOne('/api/v1/me/feedback-summary'))).flush({
      state: 'building',
      responses: 0,
      publicly_visible: true,
    });
    click(fixture, 'Edit profile');
    await shown(fixture, 'About · optional');
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(control(fixture, '#profile-about').value).toBe(revision.about);
    });
  });
});
