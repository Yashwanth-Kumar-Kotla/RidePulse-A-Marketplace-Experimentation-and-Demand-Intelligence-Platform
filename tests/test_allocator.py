from ridepulse.optimization.allocator import (
    brute_force_best,
    greedy_by_demand_allocation,
    optimize_allocation,
    uniform_allocation,
)
from ridepulse.optimization.uplift import UpliftPoint

# Small synthetic curves (not simulator output) so this test is fast and the
# expected answer is easy to reason about by hand: zone A has strong, non-
# diminishing returns; zone B saturates early (spending past $20 is pure
# waste); zone C is weak throughout.
CURVES = {
    "A": [
        UpliftPoint(zone="A", spend=0, treatment_prob=0, fulfillment_rate=0, unfulfilled_reduction=0, p90_wait_min=0),
        UpliftPoint(zone="A", spend=10, treatment_prob=0, fulfillment_rate=0, unfulfilled_reduction=5, p90_wait_min=0),
        UpliftPoint(zone="A", spend=20, treatment_prob=0, fulfillment_rate=0, unfulfilled_reduction=12, p90_wait_min=0),
    ],
    "B": [
        UpliftPoint(zone="B", spend=0, treatment_prob=0, fulfillment_rate=0, unfulfilled_reduction=0, p90_wait_min=0),
        UpliftPoint(zone="B", spend=10, treatment_prob=0, fulfillment_rate=0, unfulfilled_reduction=8, p90_wait_min=0),
        UpliftPoint(zone="B", spend=20, treatment_prob=0, fulfillment_rate=0, unfulfilled_reduction=8, p90_wait_min=0),  # saturated
    ],
    "C": [
        UpliftPoint(zone="C", spend=0, treatment_prob=0, fulfillment_rate=0, unfulfilled_reduction=0, p90_wait_min=0),
        UpliftPoint(zone="C", spend=10, treatment_prob=0, fulfillment_rate=0, unfulfilled_reduction=1, p90_wait_min=0),
        UpliftPoint(zone="C", spend=20, treatment_prob=0, fulfillment_rate=0, unfulfilled_reduction=2, p90_wait_min=0),
    ],
}


def test_optimizer_never_exceeds_budget():
    for budget in [0, 5, 15, 25, 40, 60]:
        alloc = optimize_allocation(CURVES, budget)
        assert alloc.total_spend <= budget


def test_optimizer_matches_brute_force_across_budgets():
    for budget in [0, 10, 15, 20, 25, 30, 40, 60]:
        opt = optimize_allocation(CURVES, budget)
        brute = brute_force_best(CURVES, budget)
        assert abs(opt.total_unfulfilled_reduction - brute.total_unfulfilled_reduction) < 1e-6, (
            f"budget={budget}: optimizer={opt.total_unfulfilled_reduction} brute_force={brute.total_unfulfilled_reduction}"
        )


def test_optimizer_avoids_the_saturated_dominated_option():
    # zone B's $20 level is strictly dominated by its $10 level (same
    # benefit, more cost) -- a correct optimizer should never pick it.
    alloc = optimize_allocation(CURVES, budget=100)
    assert alloc.spend_by_zone["B"] != 20


def test_uniform_and_greedy_never_exceed_budget():
    for budget in [0, 15, 25, 40]:
        assert uniform_allocation(CURVES, budget).total_spend <= budget
        assert greedy_by_demand_allocation(CURVES, budget, ["A", "B", "C"]).total_spend <= budget


def test_optimizer_is_never_worse_than_greedy_or_uniform():
    for budget in [10, 15, 20, 25, 30, 40]:
        opt = optimize_allocation(CURVES, budget)
        greedy = greedy_by_demand_allocation(CURVES, budget, ["A", "B", "C"])
        uniform = uniform_allocation(CURVES, budget)
        assert opt.total_unfulfilled_reduction >= greedy.total_unfulfilled_reduction - 1e-9
        assert opt.total_unfulfilled_reduction >= uniform.total_unfulfilled_reduction - 1e-9
