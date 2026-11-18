"""Recording start/stop conditions and the gate that applies them to incoming sensor chunks."""
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Condition:
    """kind 'measure': a measurement (key) is above/below value; kind 'time' (stop only): value = seconds."""
    kind: str
    key: str = ""
    op: str = ">"
    value: float = 0.0

    def met(self, y) -> np.ndarray:
        y = np.asarray(y, dtype=float)  # NaN compares False, so missing samples never trigger
        return y > self.value if self.op == ">" else y < self.value


@dataclass
class Conditions:
    start: Condition | None = None
    stop: Condition | None = None

    @property
    def stop_after(self) -> float | None:
        return self.stop.value if self.stop and self.stop.kind == "time" else None


class Gate:
    """Applies a Start condition (time zero = first sample that meets it) and watches a Stop condition.
    filter() runs on sensor threads; stop_hit / triggered are plain flags read by the GUI thread."""

    def __init__(self, conditions: Conditions):
        self.c = conditions
        self.t0: float | None = None if conditions.start else 0.0
        self.triggered = False
        self.stop_hit = False

    def filter(self, sensor_id: str, t, values: dict):
        t = np.asarray(t, dtype=float)
        if self.t0 is None:
            prefix, y = f"{sensor_id}:", None
            if self.c.start.key.startswith(prefix):
                y = values.get(self.c.start.key[len(prefix):])
            hit = np.flatnonzero(self.c.start.met(y)) if y is not None else []
            if len(hit) == 0:
                return None
            self.t0, self.triggered = float(t[hit[0]]), True
        t = t - self.t0
        keep = t >= 0  # another sensor's samples from before the trigger
        if not keep.all():
            t, values = t[keep], {m: np.asarray(y)[keep] for m, y in values.items()}
        stop = self.c.stop
        if stop and stop.kind == "measure" and stop.key.startswith(f"{sensor_id}:"):
            y = values.get(stop.key[len(sensor_id) + 1:])
            if y is not None and stop.met(y).any():
                self.stop_hit = True
        return t, values
