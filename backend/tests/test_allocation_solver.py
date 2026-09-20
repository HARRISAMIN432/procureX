from app.optimization.allocation import (
    Allocation,
    AllocationProblem,
    Demand,
    Offer,
    SolverOutcome,
    solve_allocation,
    validate_allocations,
)


def test_solver_finds_lowest_cost_split_and_validates_constraints() -> None:
    problem = AllocationProblem(
        demands=(Demand("item-1", 10),),
        offers=(
            Offer("item-1", "submission-1", "supplier-1", 6, 1, 100),
            Offer("item-1", "submission-2", "supplier-2", 10, 1, 120),
        ),
        fixed_supplier_costs={},
    )
    result = solve_allocation(problem)
    assert result.outcome is SolverOutcome.OPTIMAL
    assert [(line.submission_id, line.quantity) for line in result.allocations] == [
        ("submission-1", 6),
        ("submission-2", 4),
    ]
    assert result.objective == 1080
    assert all(result.constraint_checks.values())


def test_solver_honors_no_split_policy() -> None:
    result = solve_allocation(
        AllocationProblem(
            demands=(Demand("item-1", 10),),
            offers=(
                Offer("item-1", "submission-1", "supplier-1", 6, 1, 10),
                Offer("item-1", "submission-2", "supplier-2", 10, 1, 12),
            ),
            fixed_supplier_costs={},
            allow_split_awards=False,
        )
    )
    assert result.outcome is SolverOutcome.OPTIMAL
    assert len(result.allocations) == 1
    assert result.allocations[0].submission_id == "submission-2"


def test_solver_returns_actionable_capacity_infeasibility() -> None:
    result = solve_allocation(
        AllocationProblem(
            demands=(Demand("item-1", 10),),
            offers=(Offer("item-1", "submission-1", "supplier-1", 4, 1, 10),),
            fixed_supplier_costs={},
        )
    )
    assert result.outcome is SolverOutcome.INFEASIBLE
    assert result.infeasibility_reasons == ("item:item-1:capacity_shortfall:6",)


def test_solver_reports_budget_lower_bound_conflict() -> None:
    result = solve_allocation(
        AllocationProblem(
            demands=(Demand("item-1", 10),),
            offers=(Offer("item-1", "submission-1", "supplier-1", 10, 1, 10),),
            fixed_supplier_costs={},
            budget=99,
        )
    )
    assert result.outcome is SolverOutcome.INFEASIBLE
    assert "budget_below_variable_cost_lower_bound:100" in result.infeasibility_reasons


def test_independent_validation_rejects_tampered_allocation() -> None:
    problem = AllocationProblem(
        demands=(Demand("item-1", 10),),
        offers=(Offer("item-1", "submission-1", "supplier-1", 10, 1, 10),),
        fixed_supplier_costs={},
    )
    checks = validate_allocations(
        problem,
        (Allocation("item-1", "submission-1", "wrong-supplier", 10, 10, 100),),
    )
    assert checks["known_eligible_offers"] is False
    assert checks["demand_satisfied"] is False
