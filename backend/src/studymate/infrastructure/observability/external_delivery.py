"""Delivery loop observations only; technical alerts belong to Prometheus/Alertmanager."""

from time import monotonic

from opentelemetry.metrics import CallbackOptions, Meter, Observation


class ExternalDeliverySignals:
    def __init__(self, meter: Meter | None = None) -> None:
        self.available: bool | None = None
        self.at: float | None = None
        self.enabled = True
        self.cycles = meter.create_counter("worker.external.cycles") if meter else None
        if meter is not None:
            meter.create_observable_gauge(
                "worker.external.storage.available", callbacks=[self.storage]
            )
            meter.create_observable_gauge(
                "worker.external.cycle.age", callbacks=[self.age], unit="s"
            )

    def storage_available(self, available: bool) -> None:
        self.available = available
        self.at = monotonic()
        if self.cycles is not None:
            self.cycles.add(1, {"storage": "available" if available else "unavailable"})

    def storage(self, options: CallbackOptions) -> tuple[Observation, ...]:
        del options
        return (
            (Observation(int(self.available)),)
            if self.enabled and self.available is not None
            else ()
        )

    def age(self, options: CallbackOptions) -> tuple[Observation, ...]:
        del options
        return (
            (Observation(max(0, monotonic() - self.at)),)
            if self.enabled and self.at is not None
            else ()
        )

    def close(self) -> None:
        self.enabled = False
