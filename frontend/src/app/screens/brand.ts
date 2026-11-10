import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';

@Component({
  selector: 'peerly-brand',
  imports: [RouterLink],
  template: `<a routerLink="/" aria-label="Peerly home"
    ><img src="assets/brand/logo-mark.svg" width="32" height="32" alt="" />Peerly</a
  >`,
  styles: `
    a {
      display: flex;
      align-items: center;
      gap: 0.625rem;
      font: var(--tui-typography-heading-h5);
      color: inherit;
      text-decoration: none;
    }
  `,
})
export class Brand {}
