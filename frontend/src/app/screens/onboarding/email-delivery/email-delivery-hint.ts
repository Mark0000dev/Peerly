import { Component, input } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TuiLink } from '@taiga-ui/core';
import type { Api } from '../../../api.generated';

@Component({
  selector: 'peerly-email-delivery-hint',
  imports: [RouterLink, TuiLink],
  templateUrl: './email-delivery-hint.html',
})
export class EmailDeliveryHint {
  public readonly delivery =
    input.required<Api['schemas']['ChallengeStatusResponse']['delivery']>();
}
