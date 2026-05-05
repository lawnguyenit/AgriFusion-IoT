from __future__ import annotations

import math
from typing import Any

from .model import TAU_HOURS


def build_dynamics(
    pressures: dict[str, float],
    previous_state: dict[str, dict[str, float]],
) -> dict[str, Any]:
    dynamics: dict[str, Any] = {}
    for name, pressure in pressures.items():
        if not name.endswith("_pressure") and name != "sensor_uncertainty":
            continue
        prev = previous_state.get(name)
        dt_hours = float(previous_state.get("_dt_hours") or 0.0)
        tau = TAU_HOURS.get(name, 24.0)
        distance = 1.0 - pressure
        if prev is None or dt_hours <= 0:
            accumulated = pressure * max(dt_hours, 1.0)
            velocity = None
            acceleration = None
        else:
            prev_distance = prev["distance"]
            prev_velocity = prev.get("velocity")
            accumulated = math.exp(-dt_hours / tau) * prev.get("accumulated", 0.0) + pressure * dt_hours
            velocity = (prev_distance - distance) / dt_hours
            acceleration = None if prev_velocity is None else (velocity - prev_velocity) / dt_hours

        dynamics[f"{name}_distance_to_boundary"] = distance
        dynamics[f"{name}_velocity_to_boundary"] = velocity
        dynamics[f"{name}_acceleration_to_boundary"] = acceleration
        dynamics[f"{name}_accumulated_pressure"] = accumulated
        previous_state[name] = {
            "distance": distance,
            "velocity": velocity if velocity is not None else 0.0,
            "accumulated": accumulated,
        }
    return dynamics

