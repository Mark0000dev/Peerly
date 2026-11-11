import { Component, afterNextRender, inject } from '@angular/core';
import { ObservationRelease } from './observability/observation-release';
import { RouterOutlet } from '@angular/router';
import { TuiRoot } from '@taiga-ui/core';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, TuiRoot],
  template: '<tui-root><router-outlet /></tui-root>',
})
export class App {
  private readonly release = inject(ObservationRelease);
  public constructor() {
    afterNextRender(() => {
      void this.release.load();
    });
  }
}
