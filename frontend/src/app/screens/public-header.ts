import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TuiButton, TuiLink } from '@taiga-ui/core';
import { Brand } from './brand';

@Component({
  selector: 'peerly-public-header',
  imports: [Brand, RouterLink, TuiButton, TuiLink],
  template: `<header>
    <peerly-brand />
    <nav aria-label="Main navigation">
      <a tuiLink routerLink="/" fragment="how">How it works</a>
      <a tuiLink routerLink="/" fragment="safety">Safety</a>
      <a tuiLink routerLink="/help">Help</a>
    </nav>
    <a tuiButton class="open-app" routerLink="/onboarding" size="m">Open the app</a>
  </header>`,
  styles: `
    :host {
      display: block;
      background: var(--tui-background-base);
    }
    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 1rem;
      max-inline-size: 90rem;
      margin-inline: auto;
      padding: max(1rem, env(safe-area-inset-top)) max(1rem, env(safe-area-inset-right)) 1rem
        max(1rem, env(safe-area-inset-left));
    }
    .open-app {
      max-inline-size: 100%;
      white-space: normal;
      block-size: auto;
      min-block-size: var(--tui-height-m);
    }
    nav {
      display: none;
      align-items: center;
      flex-wrap: wrap;
      gap: 1.25rem;
    }
    @media (width >= 48rem) {
      header {
        padding-inline: 4rem;
      }
      nav {
        display: flex;
      }
    }
  `,
})
export class PublicHeader {}
