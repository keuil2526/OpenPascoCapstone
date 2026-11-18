"""Recorded data: runs of time series, appended from sensor threads, read by the GUI.

No Qt here so the engine can be tested and reused without a GUI.
"""
import threading
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from core.calculation import CalcError, evaluate


class Series:
    """Append-only (t, y) arrays with amortised growth."""

    def __init__(self, capacity: int = 1024):
        self._t = np.empty(capacity)
        self._y = np.empty(capacity)
        self.n = 0

    def extend(self, t: np.ndarray, y: np.ndarray):
        need = self.n + len(t)
        if need > len(self._t):
            cap = max(need, 2 * len(self._t))
            # new buffers: readers holding views of the old ones stay valid
            self._t = np.concatenate([self._t[:self.n], np.empty(cap - self.n)])
            self._y = np.concatenate([self._y[:self.n], np.empty(cap - self.n)])
        self._t[self.n:need] = t
        self._y[self.n:need] = y
        self.n = need

    def view(self) -> tuple[np.ndarray, np.ndarray]:
        return self._t[:self.n], self._y[:self.n]


@dataclass(frozen=True)
class Calc:
    """A calculated measurement. refs maps each [name] used in expr to a recorded series key."""
    key: str
    name: str
    unit: str
    expr: str
    refs: dict[str, str]


@dataclass
class Run:
    number: int
    started: datetime
    series: dict[str, Series] = field(default_factory=dict)


class DataManager:
    def __init__(self):
        self._lock = threading.RLock()
        self.runs: list[Run] = []
        self.calcs: dict[str, Calc] = {}  # touched from the GUI thread only
        self.recording = False

    def start_run(self) -> Run:
        with self._lock:
            run = Run(len(self.runs) + 1, datetime.now())
            self.runs.append(run)
            self.recording = True
            return run

    def stop_run(self):
        with self._lock:
            self.recording = False

    def append(self, key: str, t: np.ndarray, y: np.ndarray):
        if len(t) != len(y):
            raise ValueError(f"{key}: t has {len(t)} samples, y has {len(y)}")
        with self._lock:
            if not self.recording:
                return  # late samples after stop are dropped
            self.runs[-1].series.setdefault(key, Series()).extend(t, y)

    def latest(self, key: str) -> tuple[np.ndarray, np.ndarray] | None:
        """(t, y) of the newest run for key (recorded or calculated), or None.
        Recorded arrays are views: do not modify."""
        calc = self.calcs.get(key)
        if calc is not None:
            try:
                return evaluate(calc.expr, lambda n: self.latest(calc.refs[n]) if n in calc.refs else None)
            except (CalcError, RecursionError):
                return None  # e.g. no data yet; the display just stays empty
        with self._lock:
            if not self.runs or key not in self.runs[-1].series:
                return None
            return self.runs[-1].series[key].view()

    def load(self, runs: list[Run]):
        with self._lock:
            self.runs = list(runs)
            self.calcs.clear()
            self.recording = False

    def clear(self):
        with self._lock:
            self.runs.clear()
            self.calcs.clear()
            self.recording = False
