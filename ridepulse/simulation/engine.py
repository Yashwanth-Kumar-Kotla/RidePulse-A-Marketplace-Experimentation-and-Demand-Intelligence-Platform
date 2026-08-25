"""Discrete-event marketplace simulator: one zone's rider/driver queueing system.

Deliberately zone-level, not geospatial. Two simplifications kept out of
this first cut, both documented rather than silently assumed away:
1. No cross-zone driver repositioning -- a driver who completes a trip stays
   available in the same zone, instead of following the trip's real
   drop-off zone. Modeling that needs an origin-destination flow matrix per
   zone-hour, which is a real feature to add later, not a one-liner.
2. Matching is "any idle driver in the same zone," not "nearest available" --
   there's no sub-zone position to be nearest to at this grain.

Plain heapq event loop, not a DES framework (e.g. simpy): with only 3 event
types, a coroutine-based framework would add a control-flow paradigm to
learn without saving meaningful code -- every line here is inspectable
without framework knowledge.
"""

from __future__ import annotations

import heapq
import itertools
from dataclasses import dataclass

import numpy as np

ARRIVAL = "arrival"
PATIENCE_EXPIRY = "patience_expiry"
TRIP_COMPLETE = "trip_complete"


@dataclass
class SimParams:
    arrival_rate_per_hour: float
    n_drivers: int
    duration_hours: float
    mean_trip_minutes: float = 15.0
    mean_patience_minutes: float = 5.0
    seed: int = 0


@dataclass
class SimResult:
    total_arrivals: int
    completed_trips: int
    cancelled_trips: int
    wait_times_min: list[float]  # request -> match wait, completed trips only
    driver_busy_minutes: float
    n_drivers: int
    duration_hours: float

    @property
    def utilization(self) -> float:
        # Can exceed 1.0 in edge cases: a trip matched near the end of the
        # simulation window still runs its full duration, which can push
        # busy_minutes slightly past the window -- a real boundary effect in
        # any windowed observation, not a bug. Not clamped, so it's visible
        # if it happens rather than silently hidden.
        available_minutes = self.n_drivers * self.duration_hours * 60
        return self.driver_busy_minutes / available_minutes if available_minutes else 0.0

    @property
    def fulfillment_rate(self) -> float:
        total = self.completed_trips + self.cancelled_trips
        return self.completed_trips / total if total else 0.0


def run_simulation(params: SimParams) -> SimResult:
    rng = np.random.default_rng(params.seed)
    tie_breaker = itertools.count()  # heapq needs a total order; breaks ties on equal times
    event_queue: list[tuple[float, int, str, dict]] = []

    def schedule(time: float, event_type: str, payload: dict) -> None:
        heapq.heappush(event_queue, (time, next(tie_breaker), event_type, payload))

    # Pre-generate the whole arrival process up front (Poisson via exponential
    # inter-arrival times) -- simpler than generating arrivals reactively,
    # and the arrival process doesn't depend on simulator state.
    t, rider_id = 0.0, 0
    while True:
        t += rng.exponential(60.0 / params.arrival_rate_per_hour)
        if t >= params.duration_hours * 60:
            break
        schedule(t, ARRIVAL, {"rider_id": rider_id})
        rider_id += 1
    total_arrivals = rider_id

    idle_drivers = params.n_drivers
    waiting: dict[int, float] = {}  # rider_id -> arrival_time, riders not yet matched
    completed = cancelled = 0
    wait_times: list[float] = []
    busy_minutes = 0.0

    def match(time: float, arrival_time: float) -> None:
        nonlocal idle_drivers, completed, busy_minutes
        idle_drivers -= 1
        wait_times.append(time - arrival_time)
        trip_minutes = max(1.0, rng.exponential(params.mean_trip_minutes))
        busy_minutes += trip_minutes
        completed += 1
        schedule(time + trip_minutes, TRIP_COMPLETE, {})

    while event_queue:
        time, _, etype, payload = heapq.heappop(event_queue)

        if etype == ARRIVAL:
            rid = payload["rider_id"]
            if idle_drivers > 0:
                match(time, arrival_time=time)  # matched immediately, wait = 0
            else:
                waiting[rid] = time
                patience = rng.exponential(params.mean_patience_minutes)
                schedule(time + patience, PATIENCE_EXPIRY, {"rider_id": rid})

        elif etype == PATIENCE_EXPIRY:
            rid = payload["rider_id"]
            if rid in waiting:  # still unmatched -> cancels
                del waiting[rid]
                cancelled += 1

        elif etype == TRIP_COMPLETE:
            idle_drivers += 1
            if waiting:
                rid = min(waiting, key=waiting.get)  # FIFO: earliest arrival first
                arrival_time = waiting.pop(rid)
                match(time, arrival_time)

    return SimResult(
        total_arrivals=total_arrivals,
        completed_trips=completed,
        cancelled_trips=cancelled,
        wait_times_min=wait_times,
        driver_busy_minutes=busy_minutes,
        n_drivers=params.n_drivers,
        duration_hours=params.duration_hours,
    )
