import { Component, input } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TuiAutoFocus } from '@taiga-ui/cdk';
import { TuiAppBarBack } from '@taiga-ui/layout';

// A caller-owned native back control uses slot="start"; remaining content is end actions.
@Component({
  selector: 'peerly-settings-header',
  imports: [RouterLink, TuiAppBarBack, TuiAutoFocus],
  template: `<header>
    <ng-content select="[slot=start]" />
    @if (backToProfile()) {
      <a tuiAppBarBack routerLink="/profile" aria-label="Back to profile">Back</a>
    }
    <h1 [tuiAutoFocus]="autoFocus()" [attr.tabindex]="autoFocus() ? -1 : null">{{ heading() }}</h1>
    <ng-content />
  </header>`,
  styles: `
    :host {
      display: block;
      min-inline-size: 0;
      container: settings-heading / inline-size;
      font: var(--tui-typography-body-m);
    }
    header {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
      align-items: center;
      min-block-size: var(--tui-height-m);
      font-weight: 700;
      color: var(--tui-text-primary);
      background: var(--tui-background-base-alt);
    }
    a {
      justify-self: start;
    }
    h1 {
      grid-column: 2;
      min-inline-size: 0;
      margin: 0;
      font: inherit;
      text-align: center;
    }
    @container settings-heading (width < 16em) {
      header {
        grid-template-columns: minmax(0, 1fr);
        gap: 0.75rem;
      }
      h1 {
        grid-column: 1;
        text-align: start;
      }
    }
  `,
})
export class SettingsHeader {
  public readonly heading = input.required<string>();
  public readonly backToProfile = input(false);
  public readonly autoFocus = input(false);
}
