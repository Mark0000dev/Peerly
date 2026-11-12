import { Component, input } from '@angular/core';
import type { Api } from '../../../../api.generated';
import { OperatorOrigin } from '../../operator-origin';

@Component({
  selector: 'app-operator-report-review-proof',
  imports: [OperatorOrigin],
  template: `<article>
    <h4>
      {{ review().action === 'dismiss' ? 'Dismiss' : 'Escalate' }} · version {{ review().version }}
    </h4>
    <p class="reason">{{ review().reason }}</p>
    <dl>
      <div>
        <dt>Review ID</dt>
        <dd>{{ review().id }}</dd>
      </div>
      <div>
        <dt>Report ID</dt>
        <dd>{{ review().report_id }}</dd>
      </div>
      <div>
        <dt>Previous version</dt>
        <dd>{{ review().previous_version ?? 'No previous decision' }}</dd>
      </div>
      <div>
        <dt>Operator account ID</dt>
        <dd>{{ review().operator_id }}</dd>
      </div>
      <div>
        <dt>Stored grant version</dt>
        <dd>{{ review().operator_access_version }}</dd>
      </div>
      <div>
        <dt>Stored actor session ID</dt>
        <dd>{{ review().actor_session_id }}</dd>
      </div>
      <div>
        <dt>Reviewed at</dt>
        <dd>
          <time [attr.datetime]="review().reviewed_at">{{ review().reviewed_at }}</time>
        </dd>
      </div>
      <div>
        <dt>Event ID</dt>
        <dd>{{ review().event_id }}</dd>
      </div>
    </dl>
    <app-operator-origin [origin]="review()" />
  </article>`,
  styles: `
    :host,
    article {
      display: block;
      min-inline-size: 0;
      overflow-wrap: anywhere;
    }
    h4,
    p,
    dl,
    dd {
      margin: 0;
    }
    article {
      display: grid;
      gap: 0.75rem;
    }
    h4 {
      font: var(--tui-typography-body-m);
      font-weight: 600;
    }
    dl {
      display: grid;
      gap: 0.5rem;
    }
    dt {
      color: var(--tui-text-secondary);
    }
    .reason {
      white-space: pre-wrap;
    }
  `,
})
export class ReviewProof {
  public readonly review = input.required<Api['schemas']['ReportReviewResponse']>();
}
