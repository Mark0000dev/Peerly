import type {
  Action,
  ActionHandle,
  Epoch,
  ObservationInput,
  ObservationSink,
} from './observation-contract';
import type { ObservationBuffer } from './observation-buffer';
export interface ObservationBridge extends ObservationSink {
  readonly attach: (buffer: ObservationBuffer) => () => void;
}
// Root ErrorHandler/interceptor outlive the routed child QueryClient. Retain only
// an owned adapter resource handle, never a copied session/query DTO or role flag.
export function createObservationBridge(): ObservationBridge {
  let active: ObservationBuffer | null = null;
  return {
    observe: (input: ObservationInput) => active?.observe(input) ?? false,
    beginAction: (action: Action): ActionHandle | null => active?.beginAction(action) ?? null,
    epoch: (): Epoch | null => active?.epoch() ?? null,
    attach: (buffer: ObservationBuffer) => {
      active?.dispose();
      active = buffer;
      return () => {
        if (active !== buffer) return;
        active = null;
        buffer.dispose();
      };
    },
  };
}
