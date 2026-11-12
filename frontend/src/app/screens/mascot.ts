import { Component, input } from '@angular/core';

@Component({
  selector: 'peerly-mascot',
  template: `<picture>
    <source
      media="(prefers-reduced-motion: reduce)"
      [srcset]="'assets/brand/mascot-' + name() + '-still.svg'"
    />
    <img
      [src]="'assets/brand/mascot-' + name() + '.svg'"
      [width]="width()"
      [height]="height()"
      alt=""
    />
  </picture>`,
  styles: `
    :host,
    picture,
    img {
      display: block;
      max-inline-size: 100%;
    }
    img {
      block-size: auto;
    }
  `,
})
export class Mascot {
  public readonly name = input.required<'chat' | 'hello' | 'letter' | 'oops' | 'read' | 'rest'>();
  public readonly width = input(160);
  public readonly height = input(140);
}
