import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TuiButton, TuiLink } from '@taiga-ui/core';
import { TuiBlockStatus } from '@taiga-ui/layout';
import { PublicHeader } from '../public-header';
import { PublicFooter } from '../public-footer';
import { Mascot } from '../mascot';

@Component({
  selector: 'app-not-found',
  imports: [RouterLink, TuiButton, TuiLink, TuiBlockStatus, PublicHeader, PublicFooter, Mascot],
  template: `<peerly-public-header />
    <main>
      <tui-block-status>
        <peerly-mascot tuiSlot="top" name="oops" [width]="200" [height]="200" />
        <h1>Page not found</h1>
        <p>This link may have changed. You can return to Peerly or ask the team for help.</p>
        <a tuiButton routerLink="/">Back to Peerly</a>
        <a tuiLink routerLink="/help">Help and contact</a>
      </tui-block-status>
    </main>
    <peerly-public-footer />`,
  styles: `
    :host {
      display: block;
      background: var(--tui-background-base-alt);
    }
    main {
      display: grid;
      align-items: center;
      min-block-size: 60dvh;
      max-inline-size: 42rem;
      margin-inline: auto;
      padding: 2rem max(1.5rem, env(safe-area-inset-right)) 3rem
        max(1.5rem, env(safe-area-inset-left));
      overflow-wrap: anywhere;
    }
  `,
})
export class NotFound {}
