import { Component, input } from '@angular/core';
import { StudentNavigation } from './student-navigation';

@Component({
  selector: 'peerly-student-layout',
  imports: [StudentNavigation],
  host: { '[class.with-navigation]': 'navigationVisible()' },
  template: `
    <div class="scroll-region">
      <div class="page-content" [style.max-inline-size]="contentWidth()">
        <ng-content />
      </div>
    </div>
    @if (navigationVisible()) {
      <peerly-student-navigation [style.max-inline-size]="contentWidth()" />
    }
  `,
  styles: `
    :host {
      display: block;
      min-inline-size: 0;
    }
    :host(.with-navigation) {
      display: grid;
      grid-template-rows: minmax(0, 1fr) auto;
      block-size: 100dvh;
    }
    .scroll-region {
      min-block-size: 0;
      min-inline-size: 0;
    }
    :host(.with-navigation) .scroll-region {
      overflow: auto;
      scroll-padding-block: 1rem;
    }
    .page-content {
      display: grid;
      min-inline-size: 0;
      min-block-size: 100dvh;
      inline-size: 100%;
      margin-inline: auto;
    }
    :host(.with-navigation) .page-content {
      min-block-size: 100%;
    }
    peerly-student-navigation {
      inline-size: 100%;
      margin-inline: auto;
    }
  `,
})
export class StudentLayout {
  public readonly contentWidth = input('44rem');
  public readonly navigationVisible = input(true);
}
