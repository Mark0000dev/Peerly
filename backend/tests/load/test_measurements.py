import math

import pytest

from tests.load.measurements import Latency, LoadPlan, Mode, throughput


@pytest.mark.parametrize("active", [100, 250, 500])
@pytest.mark.parametrize("concurrency", [10, 25])
def test_fixture_population_is_not_request_concurrency(active: int, concurrency: int) -> None:
    plan = LoadPlan(active, concurrency, Mode.SLOW)
    assert plan.active_users == active
    assert plan.concurrency == concurrency
    assert plan.concurrency < plan.active_users


@pytest.mark.parametrize("values", [(), (-1.0,), (math.inf,), (math.nan,)])
def test_missing_invalid_or_nonfinite_samples_cannot_produce_a_pass_receipt(
    values: tuple[float, ...],
) -> None:
    with pytest.raises(ValueError, match="actual finite"):
        Latency.summarize(values)


def test_nearest_rank_percentile_uses_measured_samples() -> None:
    values = tuple(float(value) for value in range(1, 21))
    result = Latency.summarize(values)
    assert result.samples == len(values)
    assert result.maximum_seconds == max(values)
    assert result.p95_seconds == values[-2]
    assert throughput(10, 2.0) == len(values) / 4


@pytest.mark.parametrize(("active", "concurrency"), [(99, 10), (501, 25), (100, 100), (500, 0)])
def test_load_scope_cannot_expand_unboundedly(active: int, concurrency: int) -> None:
    with pytest.raises(ValueError, match="bounded population"):
        LoadPlan(active, concurrency, Mode.OFFLINE)


@pytest.mark.parametrize("seconds", [0.0, -1.0, math.inf, math.nan])
def test_throughput_cannot_hide_an_invalid_wall_interval(seconds: float) -> None:
    with pytest.raises(ValueError, match="positive wall"):
        throughput(1, seconds)
