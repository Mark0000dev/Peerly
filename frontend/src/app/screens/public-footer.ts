import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TuiLink } from '@taiga-ui/core';
import { Brand } from './brand';

@Component({
  selector: 'peerly-public-footer',
  imports: [Brand, RouterLink, TuiLink],
  template: `<footer tuiTheme="dark">
    <div>
      <peerly-brand />
      <p>Find someone to study with. For APU students.</p>
    </div>
    <nav aria-label="Footer">
      <div class="group">
        <h2>Product</h2>
        <a tuiLink appearance="action-grayscale" routerLink="/onboarding">Open the app</a>
        <a tuiLink appearance="action-grayscale" routerLink="/" fragment="how">How it works</a>
        <a tuiLink appearance="action-grayscale" routerLink="/" fragment="safety">Safety</a>
      </div>
      <div class="group">
        <h2>Help</h2>
        <a tuiLink appearance="action-grayscale" routerLink="/help">Help and contact</a>
        <a tuiLink appearance="action-grayscale" routerLink="/account/delete"
          >Delete your account</a
        >
      </div>
      <div class="group">
        <h2>Legal</h2>
        <a tuiLink appearance="action-grayscale" routerLink="/terms">Terms of Use</a>
        <a tuiLink appearance="action-grayscale" routerLink="/privacy">Privacy Policy</a>
      </div>
    </nav>
  </footer>`,
  styles: `
    :host {
      display: block;
      background: var(--tui-background-accent-opposite);
    }
    footer {
      display: grid;
      gap: 2rem;
      max-inline-size: 90rem;
      margin-inline: auto;
      padding: 2rem max(1rem, env(safe-area-inset-right)) max(2rem, env(safe-area-inset-bottom))
        max(1rem, env(safe-area-inset-left));
      color: var(--tui-text-primary);
      overflow-wrap: anywhere;
    }
    p {
      font: var(--tui-typography-body-s);
      color: var(--tui-text-secondary);
      max-inline-size: 18rem;
    }
    nav {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(min(100%, 9rem), 1fr));
      gap: 2rem;
    }
    .group {
      display: grid;
      align-content: start;
      gap: 0.75rem;
    }
    h2 {
      margin: 0;
      font: var(--tui-typography-ui-xs);
      font-weight: 700;
      text-transform: uppercase;
    }
    @media (width >= 48rem) {
      footer {
        grid-template-columns: minmax(0, 1fr) minmax(0, 2fr);
        padding-inline: 4rem;
      }
    }
  `,
})
export class PublicFooter {}
