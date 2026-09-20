import argparse
import json
import math
import platform
import statistics
import time
from dataclasses import asdict, dataclass

from app.optimization.allocation import (
    AllocationProblem,
    Demand,
    Offer,
    SolverOutcome,
    solve_allocation,
)


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    item_count: int
    supplier_count: int
    offer_count: int
    repetitions: int
    durations_ms: tuple[float, ...]
    median_ms: float
    p95_ms: float
    maximum_ms: float
    python_version: str
    platform: str


def allocation_fixture(item_count: int, supplier_count: int) -> AllocationProblem:
    if item_count <= 0 or supplier_count <= 0:
        raise ValueError("Benchmark item and supplier counts must be positive")
    demand_quantity = 100
    demands = tuple(Demand(f"item-{item}", demand_quantity) for item in range(item_count))
    offers = tuple(
        Offer(
            item_id=f"item-{item}",
            submission_id=f"submission-{supplier}",
            supplier_id=f"supplier-{supplier}",
            capacity=demand_quantity,
            minimum_quantity=1,
            unit_cost=10_000 + item * 17 + supplier * 31,
        )
        for item in range(item_count)
        for supplier in range(supplier_count)
    )
    return AllocationProblem(
        demands=demands,
        offers=offers,
        fixed_supplier_costs={
            f"supplier-{supplier}": supplier * 100 for supplier in range(supplier_count)
        },
        maximum_suppliers=supplier_count,
        timeout_seconds=30,
    )


def percentile(values: tuple[float, ...], percentile_value: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(percentile_value * len(ordered)) - 1)
    return ordered[index]


def run_allocation_benchmark(
    *, item_count: int, supplier_count: int, repetitions: int
) -> BenchmarkResult:
    if repetitions <= 0:
        raise ValueError("Benchmark repetitions must be positive")
    problem = allocation_fixture(item_count, supplier_count)
    durations: list[float] = []
    for _ in range(repetitions):
        started_at = time.perf_counter()
        result = solve_allocation(problem)
        durations.append((time.perf_counter() - started_at) * 1000)
        if result.outcome not in {SolverOutcome.OPTIMAL, SolverOutcome.FEASIBLE}:
            raise RuntimeError(f"Benchmark allocation failed with {result.outcome.value}")
        if not all(result.constraint_checks.values()):
            raise RuntimeError("Benchmark allocation failed independent validation")
    measured = tuple(round(value, 3) for value in durations)
    return BenchmarkResult(
        item_count=item_count,
        supplier_count=supplier_count,
        offer_count=item_count * supplier_count,
        repetitions=repetitions,
        durations_ms=measured,
        median_ms=round(statistics.median(measured), 3),
        p95_ms=round(percentile(measured, 0.95), 3),
        maximum_ms=round(max(measured), 3),
        python_version=platform.python_version(),
        platform=platform.platform(),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark deterministic allocation performance")
    parser.add_argument("--items", type=int, default=100)
    parser.add_argument("--suppliers", type=int, default=50)
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--maximum-p95-ms", type=float)
    arguments = parser.parse_args()
    result = run_allocation_benchmark(
        item_count=arguments.items,
        supplier_count=arguments.suppliers,
        repetitions=arguments.repetitions,
    )
    print(json.dumps(asdict(result), indent=2, sort_keys=True))
    if arguments.maximum_p95_ms is not None and result.p95_ms > arguments.maximum_p95_ms:
        parser.exit(
            1,
            f"allocation benchmark p95 {result.p95_ms} ms exceeds {arguments.maximum_p95_ms} ms\n",
        )


if __name__ == "__main__":
    main()
