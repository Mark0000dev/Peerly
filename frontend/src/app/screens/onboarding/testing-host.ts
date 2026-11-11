import type { ComponentFixture } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { NgControl } from '@angular/forms';
import type { AbstractControl } from '@angular/forms';
import { expect, vi } from 'vitest';

export function host<T>(fixture: Readonly<ComponentFixture<T>>): HTMLElement {
  const value: unknown = fixture.nativeElement;
  if (!(value instanceof HTMLElement)) throw new Error('Missing screen');
  return value;
}
export async function shown<T>(
  fixture: Readonly<ComponentFixture<T>>,
  text: string,
): Promise<void> {
  await vi.waitFor(() => {
    fixture.detectChanges();
    expect(host(fixture).textContent).toContain(text);
  });
}
export function control<T>(
  fixture: Readonly<ComponentFixture<T>>,
  selector = 'input',
): Readonly<AbstractControl<unknown>> {
  const field = fixture.debugElement.query(By.css(selector)).injector.get(NgControl).control;
  if (field === null) throw new Error('Missing control');
  return field;
}
export function submit<T>(fixture: Readonly<ComponentFixture<T>>): void {
  const form = host(fixture).querySelector('form');
  if (!(form instanceof HTMLFormElement)) throw new Error('Missing form');
  form.requestSubmit();
}
export function click<T>(fixture: Readonly<ComponentFixture<T>>, label: string): void {
  const element = Array.from(host(fixture).querySelectorAll('button')).find(
    (native: Readonly<HTMLButtonElement>) => native.textContent.trim() === label,
  );
  if (element === undefined) throw new Error(`Missing action ${label}`);
  element.click();
}
