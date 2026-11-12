"""Bounded population/concurrency contracts and content-free measurements."""

import math
from dataclasses import dataclass
from enum import StrEnum
from math import ceil

POPULATION = 500
ACTIVE_STEPS = (100, 250, 500)
CONCURRENCY_STEPS = (10, 25)
CORE_LIMIT_SECONDS = 2.0
AI_LIMIT_SECONDS = 3.0
MAX_CORE_SAMPLES = 1000


class Mode(StrEnum):
    SLOW = "slow"
    OFFLINE = "offline"


@dataclass(frozen=True, slots=True)
class LoadPlan:
    active_users: int
    concurrency: int
    mode: Mode

    def __post_init__(self) -> None:
        if self.active_users not in ACTIVE_STEPS or self.concurrency not in CONCURRENCY_STEPS:
            raise ValueError("Load plan must use the bounded population/concurrency steps")
        if not isinstance(self.mode, Mode):
            raise ValueError("Load requires an explicit controlled executor mode")


@dataclass(frozen=True, slots=True)
class Latency:
    samples: int
    maximum_seconds: float
    p95_seconds: float

    @classmethod
    def summarize(cls, values: tuple[float, ...]) -> "Latency":
        if not values or any(not math.isfinite(value) or value < 0 for value in values):
            raise ValueError("Latency requires actual finite nonnegative observations")
        ordered = sorted(values)
        return cls(len(values), ordered[-1], ordered[ceil(len(values) * 0.95) - 1])


def throughput(attempts: int, elapsed_seconds: float) -> float:
    if attempts < 1 or not math.isfinite(elapsed_seconds) or elapsed_seconds <= 0:
        raise ValueError("Throughput requires actual attempts and a positive wall interval")
    return attempts / elapsed_seconds
