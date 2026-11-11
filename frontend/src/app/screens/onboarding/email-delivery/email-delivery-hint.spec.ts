import { TestBed } from '@angular/core/testing';
import type { ComponentFixture } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import type { Api } from '../../../api.generated';
import { EmailDeliveryHint } from './email-delivery-hint';

describe('Email delivery help distinguishes service acceptance from inbox delivery', () => {
  let fixture: ComponentFixture<EmailDeliveryHint>;
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideRouter([])] });
    fixture = TestBed.createComponent(EmailDeliveryHint);
  });
  afterEach(() => {
    fixture.destroy();
    TestBed.resetTestingModule();
  });
  function render(delivery: Api['schemas']['ChallengeStatusResponse']['delivery']): HTMLElement {
    fixture.componentRef.setInput('delivery', delivery);
    fixture.detectChanges();
    const element: unknown = fixture.nativeElement;
    if (!(element instanceof HTMLElement)) throw new Error('Missing delivery help host');
    return element;
  }
  function text(element: Readonly<Element> | null): string {
    if (element === null) throw new Error('Missing delivery help content');
    return element.textContent.replace(/\s+/g, ' ').trim();
  }
  it('sent confirms acceptance only and keeps missing-code support visible', () => {
    const element = render('sent');
    expect(text(element.querySelector('[role="status"]'))).toContain('The mail service accepted');
    expect(text(element)).toContain('This does not confirm delivery to your inbox');
    expect(text(element)).toContain('APU’s email filters may hold messages in quarantine');
    expect(text(element)).toContain('Junk Email');
    expect(element.querySelector('a[href="/help/contact"]')?.getAttribute('href')).toBe(
      '/help/contact',
    );
    expect(element.querySelector('form,button,input')).toBeNull();
  });
  it.each(['queued', 'sending'] as const)(
    '%s does not promise acceptance or inbox delivery',
    (delivery) => {
      const element = render(delivery);
      expect(element.querySelector('[role="status"]')).not.toBeNull();
      expect(text(element)).toContain(
        delivery === 'queued' ? 'not confirmed acceptance yet' : 'Acceptance is not confirmed yet',
      );
      expect(text(element)).not.toContain('The mail service accepted your verification email');
      expect(element.querySelector('a[href="/help/contact"]')?.getAttribute('href')).toBe(
        '/help/contact',
      );
    },
  );
  it.each(['failed', 'cancelled'] as const)(
    '%s leaves outcome uncertain instead of claiming nothing was sent',
    (delivery) => {
      const element = render(delivery);
      expect(text(element.querySelector('[role="alert"]'))).toContain('couldn’t confirm');
      expect(text(element)).toContain('Check your mailbox in case it arrives');
      expect(text(element)).not.toContain('Nothing was sent');
      expect(element.querySelector('a[href="/help/contact"]')?.getAttribute('href')).toBe(
        '/help/contact',
      );
    },
  );
  it('links to the approved quarantine portal with tenant-permission guidance and safe new tab', () => {
    const element = render('sent');
    const portal = element.querySelector('a[href="https://security.microsoft.com/quarantine"]');
    expect(portal).not.toBeNull();
    expect(portal?.getAttribute('target')).toBe('_blank');
    expect(portal?.getAttribute('rel')).toBe('noopener noreferrer');
    expect(text(portal)).toContain('opens in a new tab');
    expect(text(element)).toContain('request its release if those options are available');
    expect(text(element)).toContain('If access is denied, contact APU IT');
    expect(element.querySelector('a[href="/help/contact"]')?.getAttribute('href')).toBe(
      '/help/contact',
    );
  });
  it('updates the input without retaining the previous acceptance message', () => {
    render('sent');
    const element = render('sending');
    expect(text(element)).not.toContain('The mail service accepted your verification email');
    expect(element.querySelectorAll('[role="status"]')).toHaveLength(1);
    expect(text(element)).toContain('Acceptance is not confirmed yet');
    render('failed');
    expect(element.querySelector('[role="status"]')).toBeNull();
    expect(element.querySelectorAll('[role="alert"]')).toHaveLength(1);
  });
});
