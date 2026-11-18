"""Simulated sensors so the app can be developed and demonstrated without PASCO hardware."""
import threading
import time
from typing import Callable

import numpy as np

from hardware.base import Measurement, SampleCallback, Sensor

CHUNK_SECONDS = 0.02  # deliver samples in ~20 ms batches


class SimulatedSensor(Sensor):
    def __init__(self, sensor_id: str, name: str,
                 signals: dict[Measurement, Callable[[np.ndarray, np.random.Generator], np.ndarray]]):
        self.id, self.name = sensor_id, name
        self.measurements = list(signals)
        self._signals = signals
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self, rate_hz: float, on_samples: SampleCallback) -> None:
        if self._thread:
            raise RuntimeError(f"{self.name} already running")
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, args=(rate_hz, on_samples),
                                        name=f"sim-{self.id}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._thread:
            self._stop.set()
            self._thread.join()
            self._thread = None

    def _run(self, rate_hz, on_samples):
        rng = np.random.default_rng()
        sent = 0
        t0 = time.monotonic()
        while not self._stop.wait(CHUNK_SECONDS):
            due = int((time.monotonic() - t0) * rate_hz)  # samples that should exist by now
            if due <= sent:
                continue
            t = np.arange(sent, due) / rate_hz  # ideal sample times, like a hardware clock
            on_samples(self.id, t, {m.id: f(t, rng) for m, f in self._signals.items()})
            sent = due


def scan() -> list[Sensor]:
    """Return the simulated sensors (always available)."""
    pos = Measurement("position", "위치", "m", -1.0, 1.0)
    vel = Measurement("velocity", "속도", "m/s", -3.2, 3.2)
    temp = Measurement("temperature", "온도", "°C", 20.0, 30.0)
    w = 2 * np.pi * 0.5  # 0.5 Hz oscillation
    return [
        SimulatedSensor("sim-motion", "가상 운동 센서", {
            pos: lambda t, rng: np.sin(w * t) + rng.normal(0, 0.005, t.size),
            vel: lambda t, rng: w * np.cos(w * t) + rng.normal(0, 0.02, t.size),
        }),
        SimulatedSensor("sim-temp", "가상 온도 센서", {
            temp: lambda t, rng: 25 + 2 * (1 - np.exp(-t / 20)) + rng.normal(0, 0.05, t.size),
        }),
    ]
