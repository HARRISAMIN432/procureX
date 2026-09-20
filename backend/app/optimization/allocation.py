from dataclasses import dataclass
from enum import StrEnum

from ortools.sat.python import cp_model


class SolverOutcome(StrEnum):
    OPTIMAL = "optimal"
    FEASIBLE = "feasible"
    INFEASIBLE = "infeasible"
    UNKNOWN = "unknown"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class Demand:
    item_id: str
    quantity: int


@dataclass(frozen=True, slots=True)
class Offer:
    item_id: str
    submission_id: str
    supplier_id: str
    capacity: int
    minimum_quantity: int
    unit_cost: int


@dataclass(frozen=True, slots=True)
class AllocationProblem:
    demands: tuple[Demand, ...]
    offers: tuple[Offer, ...]
    fixed_supplier_costs: dict[str, int]
    budget: int | None = None
    maximum_suppliers: int | None = None
    allow_split_awards: bool = True
    timeout_seconds: float = 30


@dataclass(frozen=True, slots=True)
class Allocation:
    item_id: str
    submission_id: str
    supplier_id: str
    quantity: int
    unit_cost: int
    extended_cost: int


@dataclass(frozen=True, slots=True)
class AllocationResult:
    outcome: SolverOutcome
    allocations: tuple[Allocation, ...]
    objective: int | None
    best_bound: int | None
    relative_gap: float | None
    runtime_ms: int
    constraint_checks: dict[str, bool]
    infeasibility_reasons: tuple[str, ...]


def diagnose_infeasibility(problem: AllocationProblem) -> tuple[str, ...]:
    reasons: list[str] = []
    for demand in problem.demands:
        offers = [offer for offer in problem.offers if offer.item_id == demand.item_id]
        capacity = sum(offer.capacity for offer in offers)
        if not offers:
            reasons.append(f"item:{demand.item_id}:no_eligible_offers")
        elif capacity < demand.quantity:
            reasons.append(f"item:{demand.item_id}:capacity_shortfall:{demand.quantity - capacity}")
        if not problem.allow_split_awards and not any(
            offer.capacity >= demand.quantity and offer.minimum_quantity <= demand.quantity
            for offer in offers
        ):
            reasons.append(f"item:{demand.item_id}:no_single_offer_can_fill_demand")
    if problem.maximum_suppliers == 0:
        reasons.append("maximum_suppliers_is_zero")
    if problem.budget is not None:
        lower_bound = 0
        for demand in problem.demands:
            costs = [
                offer.unit_cost
                for offer in problem.offers
                if offer.item_id == demand.item_id and offer.capacity > 0
            ]
            if costs:
                lower_bound += min(costs) * demand.quantity
        if lower_bound > problem.budget:
            reasons.append(f"budget_below_variable_cost_lower_bound:{lower_bound}")
    return tuple(reasons or ["combined_constraints_are_infeasible"])


def validate_allocations(
    problem: AllocationProblem, allocations: tuple[Allocation, ...]
) -> dict[str, bool]:
    demand_by_item = {item.item_id: item.quantity for item in problem.demands}
    offer_by_key = {(offer.item_id, offer.submission_id): offer for offer in problem.offers}
    allocated_by_item = {item_id: 0 for item_id in demand_by_item}
    selected_suppliers: set[str] = set()
    capacity_ok = True
    minimum_ok = True
    known_offers = True
    variable_cost = 0
    selected_per_item: dict[str, int] = {item_id: 0 for item_id in demand_by_item}
    seen_offers: set[tuple[str, str]] = set()
    for allocation in allocations:
        key = (allocation.item_id, allocation.submission_id)
        offer = offer_by_key.get(key)
        if (
            offer is None
            or key in seen_offers
            or allocation.quantity <= 0
            or allocation.supplier_id != offer.supplier_id
            or allocation.unit_cost != offer.unit_cost
            or allocation.extended_cost != allocation.quantity * offer.unit_cost
        ):
            known_offers = False
            continue
        seen_offers.add(key)
        allocated_by_item[allocation.item_id] += allocation.quantity
        selected_per_item[allocation.item_id] += 1
        selected_suppliers.add(allocation.supplier_id)
        capacity_ok &= allocation.quantity <= offer.capacity
        minimum_ok &= allocation.quantity >= offer.minimum_quantity
        variable_cost += allocation.quantity * offer.unit_cost
    total_cost = variable_cost + sum(
        problem.fixed_supplier_costs.get(supplier_id, 0) for supplier_id in selected_suppliers
    )
    return {
        "known_eligible_offers": known_offers,
        "demand_satisfied": allocated_by_item == demand_by_item,
        "capacity_respected": capacity_ok,
        "minimum_quantity_respected": minimum_ok,
        "split_policy_respected": problem.allow_split_awards
        or all(count <= 1 for count in selected_per_item.values()),
        "supplier_limit_respected": problem.maximum_suppliers is None
        or len(selected_suppliers) <= problem.maximum_suppliers,
        "budget_respected": problem.budget is None or total_cost <= problem.budget,
    }


def solve_allocation(problem: AllocationProblem) -> AllocationResult:
    model = cp_model.CpModel()
    offer_vars: list[tuple[Offer, cp_model.IntVar, cp_model.IntVar]] = []
    suppliers = sorted({offer.supplier_id for offer in problem.offers})
    supplier_vars = {supplier: model.new_bool_var(f"supplier_{supplier}") for supplier in suppliers}
    for index, offer in enumerate(problem.offers):
        quantity = model.new_int_var(0, offer.capacity, f"quantity_{index}")
        selected = model.new_bool_var(f"offer_{index}")
        model.add(quantity <= offer.capacity * selected)
        model.add(quantity >= offer.minimum_quantity * selected)
        model.add(selected <= supplier_vars[offer.supplier_id])
        offer_vars.append((offer, quantity, selected))

    for supplier_id, supplier_selected in supplier_vars.items():
        selections = [
            selected for offer, _, selected in offer_vars if offer.supplier_id == supplier_id
        ]
        model.add(supplier_selected <= sum(selections))

    for demand in problem.demands:
        matching = [
            (quantity, selected)
            for offer, quantity, selected in offer_vars
            if offer.item_id == demand.item_id
        ]
        model.add(sum(quantity for quantity, _ in matching) == demand.quantity)
        if not problem.allow_split_awards:
            model.add(sum(selected for _, selected in matching) <= 1)

    if problem.maximum_suppliers is not None:
        model.add(sum(supplier_vars.values()) <= problem.maximum_suppliers)

    variable_cost = sum(offer.unit_cost * quantity for offer, quantity, _ in offer_vars)
    fixed_cost = sum(
        problem.fixed_supplier_costs.get(supplier_id, 0) * selected
        for supplier_id, selected in supplier_vars.items()
    )
    total_cost = variable_cost + fixed_cost
    if problem.budget is not None:
        model.add(total_cost <= problem.budget)
    model.minimize(total_cost)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = problem.timeout_seconds
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 0
    status = solver.solve(model)
    outcome = {
        cp_model.OPTIMAL: SolverOutcome.OPTIMAL,
        cp_model.FEASIBLE: SolverOutcome.FEASIBLE,
        cp_model.INFEASIBLE: SolverOutcome.INFEASIBLE,
        cp_model.MODEL_INVALID: SolverOutcome.INVALID,
        cp_model.UNKNOWN: SolverOutcome.UNKNOWN,
    }[status]
    runtime_ms = int(solver.wall_time * 1000)
    if outcome not in {SolverOutcome.OPTIMAL, SolverOutcome.FEASIBLE}:
        return AllocationResult(
            outcome=outcome,
            allocations=(),
            objective=None,
            best_bound=None,
            relative_gap=None,
            runtime_ms=runtime_ms,
            constraint_checks={},
            infeasibility_reasons=(
                diagnose_infeasibility(problem)
                if outcome is SolverOutcome.INFEASIBLE
                else ("solver_returned_no_feasible_solution",)
            ),
        )

    allocations = tuple(
        Allocation(
            item_id=offer.item_id,
            submission_id=offer.submission_id,
            supplier_id=offer.supplier_id,
            quantity=solver.value(quantity),
            unit_cost=offer.unit_cost,
            extended_cost=solver.value(quantity) * offer.unit_cost,
        )
        for offer, quantity, _ in offer_vars
        if solver.value(quantity) > 0
    )
    objective = int(round(solver.objective_value))
    best_bound = int(round(solver.best_objective_bound))
    gap = 0.0 if objective == 0 else max(0.0, (objective - best_bound) / abs(objective))
    checks = validate_allocations(problem, allocations)
    if not all(checks.values()):
        raise ValueError("Solver returned an allocation that failed independent validation")
    return AllocationResult(
        outcome=outcome,
        allocations=allocations,
        objective=objective,
        best_bound=best_bound,
        relative_gap=gap,
        runtime_ms=runtime_ms,
        constraint_checks=checks,
        infeasibility_reasons=(),
    )
