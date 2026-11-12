import { Component, signal } from '@angular/core';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { TestBed } from '@angular/core/testing';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { QueryClient, provideTanStackQuery } from '@tanstack/angular-query-experimental';
import { describe, expect, it } from 'vitest';
import { appConfig } from '../app.config';
import { StudentLayout } from './student-layout';

@Component({
  imports: [StudentLayout, ReactiveFormsModule],
  template: `
    <peerly-student-layout [navigationVisible]="navigation()">
      <main><input aria-label="Unsent draft" [formControl]="draft" /></main>
    </peerly-student-layout>
  `,
})
class LayoutHost {
  public readonly navigation = signal(true);
  public readonly draft = new FormControl('Unsent message', { nonNullable: true });
}

describe('student viewport layout content lifetime', () => {
  it('preserves the actual form and projected node when chat detail hides navigation and returns', () => {
    const client = new QueryClient();
    TestBed.configureTestingModule({
      providers: [...appConfig.providers, provideHttpClientTesting(), provideTanStackQuery(client)],
    });
    const fixture = TestBed.createComponent(LayoutHost);
    const http = TestBed.inject(HttpTestingController);
    try {
      fixture.detectChanges();
      const element: unknown = fixture.nativeElement;
      if (!(element instanceof HTMLElement)) throw new Error('Missing layout host');
      const input = element.querySelector('input');
      expect(input).toBeInstanceOf(HTMLInputElement);
      expect(element.querySelector('nav[aria-label="Student navigation"]')).not.toBeNull();
      fixture.componentInstance.draft.setValue('Keep this exact unsent draft');
      fixture.componentInstance.navigation.set(false);
      fixture.detectChanges();
      expect(element.querySelector('input')).toBe(input);
      expect(element.querySelector('nav[aria-label="Student navigation"]')).toBeNull();
      expect(fixture.componentInstance.draft.value).toBe('Keep this exact unsent draft');
      fixture.componentInstance.navigation.set(true);
      fixture.detectChanges();
      expect(element.querySelector('input')).toBe(input);
      expect(element.querySelector('nav[aria-label="Student navigation"]')).not.toBeNull();
      expect(fixture.componentInstance.draft.value).toBe('Keep this exact unsent draft');
    } finally {
      fixture.destroy();
      client.clear();
      http.verify();
      TestBed.resetTestingModule();
    }
  });
});
