"""Low-cardinality SSE observations; publication-to-send lag is not a read receipt."""

from datetime import UTC, datetime

from opentelemetry.metrics import CallbackOptions, Meter, Observation

from studymate.application.changes.observations import StreamEnd, StreamFrame, StreamSend


class StreamSignals:
    def __init__(self, meter: Meter) -> None:
        self.active = 0
        self.enabled = True
        self.closed = meter.create_counter("sse.connections.closed")
        self.frames = meter.create_counter("sse.frames")
        self.resets = meter.create_counter("sse.resets")
        self.lag = meter.create_histogram("sse.delivery.lag", unit="s")
        self.duration = meter.create_histogram("sse.send.duration", unit="s")
        meter.create_observable_gauge("sse.connections.active", callbacks=[self.connections])

    def connections(self, options: CallbackOptions) -> tuple[Observation, ...]:
        del options
        return (Observation(self.active),) if self.enabled else ()

    def stream(self) -> "ObservedStream":
        return ObservedStream(self)

    def close(self) -> None:
        self.enabled = False


class ObservedStream:
    def __init__(self, signals: StreamSignals) -> None:
        self.signals = signals
        self.active = False

    def opened(self) -> None:
        if self.active:
            raise RuntimeError("A stream observation cannot be opened twice")
        self.active = True
        self.signals.active += 1

    def closed(self, reason: StreamEnd) -> None:
        if not self.active:
            return
        self.active = False
        self.signals.active -= 1
        self.signals.closed.add(1, {"reason": reason.value})

    def frame(self, kind: StreamFrame, published_at: datetime | None = None) -> None:
        self.signals.frames.add(1, {"kind": kind.value})
        if kind == StreamFrame.RESET:
            self.signals.resets.add(1)
        if kind == StreamFrame.CHANGE and published_at is not None:
            self.signals.lag.record(max(0, (datetime.now(UTC) - published_at).total_seconds()))

    def sent(self, seconds: float, *, outcome: StreamSend) -> None:
        self.signals.duration.record(max(0, seconds), {"outcome": outcome.value})
