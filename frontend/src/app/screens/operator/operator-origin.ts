import { Component, input } from '@angular/core';
import type { Api } from '../../api.generated';

@Component({
  selector: 'app-operator-origin',
  template: `<dl>
    <div>
      <dt>HTTP request ID</dt>
      <dd>{{ origin().http_request_id ?? 'Not recorded' }}</dd>
    </div>
    <div>
      <dt>Action ID</dt>
      <dd>{{ origin().action_id ?? 'Not recorded' }}</dd>
    </div>
    <div>
      <dt>Trace ID</dt>
      <dd>{{ origin().trace_id ?? 'Not recorded' }}</dd>
    </div>
    <div>
      <dt>Span ID</dt>
      <dd>{{ origin().span_id ?? 'Not recorded' }}</dd>
    </div>
  </dl>`,
  styles: `
    :host,
    dl,
    dl > div {
      display: block;
      min-inline-size: 0;
    }
    dt,
    dd {
      overflow-wrap: anywhere;
    }
    dd {
      margin-inline: 0;
      white-space: pre-wrap;
    }
    dl {
      display: grid;
      gap: 0.75rem;
    }
  `,
})
export class OperatorOrigin {
  public readonly origin = input.required<Api['schemas']['OperatorEventOriginResponse']>();
}
