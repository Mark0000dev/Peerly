"""Plan-only retention of verified backup generations; no deletion capability."""

from dataclasses import dataclass
from datetime import UTC, datetime

MAX_RETENTION_BUCKETS = 365


@dataclass(frozen=True, slots=True)
class VerifiedRun:
    run_id: str
    at: datetime


@dataclass(frozen=True, slots=True)
class Retention:
    daily: int
    weekly: int
    monthly: int

    def __post_init__(self) -> None:
        if any(
            type(value) is not int or not 1 <= value <= MAX_RETENTION_BUCKETS
            for value in (
                self.daily,
                self.weekly,
                self.monthly,
            )
        ):
            raise ValueError("retention_bounds")


def plan(runs: tuple[VerifiedRun, ...], policy: Retention) -> dict[str, object]:
    if any(item.at.utcoffset() is None for item in runs):
        raise ValueError("aware_retention_time_required")
    ordered = sorted(runs, key=lambda item: (item.at.astimezone(UTC), item.run_id), reverse=True)
    keep: set[str] = set()
    seen: tuple[set[str], set[str], set[str]] = (set(), set(), set())
    limits = (policy.daily, policy.weekly, policy.monthly)
    for run in ordered:
        at = run.at.astimezone(UTC)
        buckets = (at.strftime("%Y-%m-%d"), at.strftime("%G-%V"), at.strftime("%Y-%m"))
        for bucket, visited, maximum in zip(buckets, seen, limits, strict=True):
            if bucket not in visited and len(visited) < maximum:
                keep.add(run.run_id)
                visited.add(bucket)
    return {
        "mode": "plan_only",
        "remote_deletion_enabled": False,
        "keep": sorted(keep),
        "review_candidates": [item.run_id for item in ordered if item.run_id not in keep],
        "unknown_or_uncommitted_prefixes": "never_delete_automatically",
    }
