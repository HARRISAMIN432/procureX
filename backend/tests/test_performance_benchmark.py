import pytest

from app.admin.performance_benchmark import (
    allocation_fixture,
    percentile,
    run_allocation_benchmark,
)


def test_allocation_benchmark_fixture_has_expected_shape() -> None:
    problem = allocation_fixture(item_count=3, supplier_count=4)
    assert len(problem.demands) == 3
    assert len(problem.offers) == 12
    assert problem.maximum_suppliers == 4
    assert problem.timeout_seconds == 30


def test_allocation_benchmark_runs_and_reports_environment() -> None:
    result = run_allocation_benchmark(item_count=2, supplier_count=3, repetitions=2)
    assert result.offer_count == 6
    assert len(result.durations_ms) == 2
    assert result.p95_ms >= 0
    assert result.maximum_ms >= result.median_ms
    assert result.python_version
    assert result.platform


def test_benchmark_validates_inputs_and_percentile() -> None:
    with pytest.raises(ValueError, match="positive"):
        allocation_fixture(item_count=0, supplier_count=1)
    with pytest.raises(ValueError, match="positive"):
        run_allocation_benchmark(item_count=1, supplier_count=1, repetitions=0)
    assert percentile((1.0, 2.0, 3.0, 4.0), 0.95) == 4.0
