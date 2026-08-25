"""Allocate a fixed incentive budget across zones to maximize total
unfulfilled-demand reduction (multi-choice knapsack: exactly one spend
level per zone), using PuLP -- a real MILP solver, not a hand-rolled one.

Also implements two baselines evaluated the identical way: uniform spend
and greedy-by-real-demand, so all three are compared on equal footing.
"""

from __future__ import annotations

from dataclasses import dataclass

import pulp

from ridepulse.optimization.uplift import UpliftPoint


@dataclass
class Allocation:
    method: str
    spend_by_zone: dict[int, float]
    total_spend: float
    total_unfulfilled_reduction: float
    points_by_zone: dict[int, UpliftPoint]  # the chosen UpliftPoint per zone


def optimize_allocation(curves: dict[int, list[UpliftPoint]], budget: float) -> Allocation:
    """Multi-choice knapsack: pick exactly one spend level per zone maximizing
    total unfulfilled_reduction, subject to total spend <= budget."""
    prob = pulp.LpProblem("incentive_allocation", pulp.LpMaximize)
    choice_vars = {
        (zone, i): pulp.LpVariable(f"choose_{zone}_{i}", cat="Binary")
        for zone, points in curves.items()
        for i in range(len(points))
    }

    prob += pulp.lpSum(
        choice_vars[(zone, i)] * points[i].unfulfilled_reduction
        for zone, points in curves.items()
        for i in range(len(points))
    )
    prob += (
        pulp.lpSum(
            choice_vars[(zone, i)] * points[i].spend for zone, points in curves.items() for i in range(len(points))
        )
        <= budget
    )
    for zone, points in curves.items():
        prob += pulp.lpSum(choice_vars[(zone, i)] for i in range(len(points))) == 1

    prob.solve(pulp.PULP_CBC_CMD(msg=0))
    if pulp.LpStatus[prob.status] != "Optimal":
        raise RuntimeError(f"allocator did not find an optimal solution: {pulp.LpStatus[prob.status]}")

    return _build_allocation("optimizer", curves, choice_vars)


def _build_allocation(method: str, curves: dict[int, list[UpliftPoint]], choice_vars: dict) -> Allocation:
    spend_by_zone, points_by_zone = {}, {}
    for zone, points in curves.items():
        for i, point in enumerate(points):
            if choice_vars[(zone, i)].value() == 1:
                spend_by_zone[zone] = point.spend
                points_by_zone[zone] = point
                break
    return Allocation(
        method=method,
        spend_by_zone=spend_by_zone,
        total_spend=sum(spend_by_zone.values()),
        total_unfulfilled_reduction=sum(p.unfulfilled_reduction for p in points_by_zone.values()),
        points_by_zone=points_by_zone,
    )


def _nearest_affordable_point(points: list[UpliftPoint], max_spend: float) -> UpliftPoint:
    affordable = [p for p in points if p.spend <= max_spend]
    return max(affordable, key=lambda p: p.spend)  # highest spend <= max_spend, points are sorted ascending


def uniform_allocation(curves: dict[int, list[UpliftPoint]], budget: float) -> Allocation:
    per_zone_budget = budget / len(curves)
    spend_by_zone, points_by_zone = {}, {}
    for zone, points in curves.items():
        chosen = _nearest_affordable_point(points, per_zone_budget)
        spend_by_zone[zone] = chosen.spend
        points_by_zone[zone] = chosen
    return Allocation(
        method="uniform",
        spend_by_zone=spend_by_zone,
        total_spend=sum(spend_by_zone.values()),
        total_unfulfilled_reduction=sum(p.unfulfilled_reduction for p in points_by_zone.values()),
        points_by_zone=points_by_zone,
    )


def greedy_by_demand_allocation(
    curves: dict[int, list[UpliftPoint]], budget: float, zones_by_demand_desc: list[int]
) -> Allocation:
    """Give the highest-real-demand zone as much as the budget allows (its
    max grid spend), then move to the next zone with whatever remains."""
    remaining = budget
    spend_by_zone, points_by_zone = {}, {}
    for zone in zones_by_demand_desc:
        points = curves[zone]
        chosen = _nearest_affordable_point(points, remaining)
        spend_by_zone[zone] = chosen.spend
        points_by_zone[zone] = chosen
        remaining -= chosen.spend
    return Allocation(
        method="greedy_by_demand",
        spend_by_zone=spend_by_zone,
        total_spend=sum(spend_by_zone.values()),
        total_unfulfilled_reduction=sum(p.unfulfilled_reduction for p in points_by_zone.values()),
        points_by_zone=points_by_zone,
    )


def brute_force_best(curves: dict[int, list[UpliftPoint]], budget: float) -> Allocation:
    """Exhaustive search over every combination of one spend level per zone --
    a correctness cross-check for optimize_allocation, not meant for
    production use (scales as len(points)^n_zones)."""
    import itertools

    zones = list(curves.keys())
    grids = [range(len(curves[z])) for z in zones]
    best = None
    for combo in itertools.product(*grids):
        points = [curves[zones[j]][combo[j]] for j in range(len(zones))]
        total_spend = sum(p.spend for p in points)
        if total_spend > budget:
            continue
        total_reduction = sum(p.unfulfilled_reduction for p in points)
        if best is None or total_reduction > best[0]:
            best = (total_reduction, {zones[j]: points[j] for j in range(len(zones))})

    total_reduction, points_by_zone = best
    return Allocation(
        method="brute_force",
        spend_by_zone={z: p.spend for z, p in points_by_zone.items()},
        total_spend=sum(p.spend for p in points_by_zone.values()),
        total_unfulfilled_reduction=total_reduction,
        points_by_zone=points_by_zone,
    )
