import { Component } from '@angular/core';
import { TuiCell, TuiIcon, TuiTitle } from '@taiga-ui/core';

@Component({
  selector: 'app-deletion-consequences',
  imports: [TuiCell, TuiIcon, TuiTitle],
  template: `<ul>
    <li tuiCell="m">
      <span class="consequence-content">
        <tui-icon icon="@tui.log-out" aria-hidden="true" />
        <span tuiTitle>All sessions for this account end.</span>
      </span>
    </li>
    <li tuiCell="m">
      <span class="consequence-content">
        <tui-icon icon="@tui.user-x" aria-hidden="true" />
        <span tuiTitle>People you talked to see “Deleted account”.</span>
      </span>
    </li>
    <li tuiCell="m">
      <span class="consequence-content">
        <tui-icon icon="@tui.inbox" aria-hidden="true" />
        <span tuiTitle>Open requests close; you leave Discover.</span>
      </span>
    </li>
    <li tuiCell="m">
      <span class="consequence-content">
        <tui-icon icon="@tui.message-circle" aria-hidden="true" />
        <span tuiTitle>Your messages stay readable to them.</span>
      </span>
    </li>
  </ul>`,
  styles: `
    :host {
      display: block;
      min-inline-size: 0;
    }
    ul {
      list-style: none;
      padding: 0;
      margin: 0;
    }
    li + li {
      margin-block-start: 0.5rem;
    }
    .consequence-content {
      display: grid;
      grid-template-columns: auto minmax(0, 1fr);
      align-items: center;
      gap: 0.75rem;
      inline-size: 100%;
      min-inline-size: 0;
    }
    @container account-settings (width < 20em) {
      .consequence-content {
        grid-template-columns: minmax(0, 1fr);
      }
    }
  `,
})
export class DeletionConsequences {}
