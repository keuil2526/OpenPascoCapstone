"""Hardware-independent sensor interface. Every driver (simulated, BLE, USB) implements Sensor."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable

import numpy as np


@dataclass(frozen=True)
class Measurement:
    id: str
    name: str
    unit: str
    minimum: float  # typical display range, used e.g. for meter scale
    maximum: float

    @property
    def label(self) -> str:
        return f"{self.name} ({self.unit})" if self.unit else self.name


# on_samples(sensor_id, t, {measurement_id: values}); t and values are equal-length 1-D arrays.
# Called from the driver's own thread.
SampleCallback = Callable[[str, np.ndarray, dict[str, np.ndarray]], None]


class Sensor(ABC):
    id: str
    name: str
    measurements: list[Measurement]
    # Set by the app. Drivers call it (from their thread) with a message when sampling dies,
    # e.g. a lost Bluetooth connection.
    on_error: Callable[[str], None] | None = None

    @abstractmethod
    def start(self, rate_hz: float, on_samples: SampleCallback) -> None:
        """Begin sampling at rate_hz. t starts at 0 for each start()."""

    @abstractmethod
    def stop(self) -> None:
        """Stop sampling. Must not return until no more callbacks will fire."""

    def close(self) -> None:
        """Release the device (disconnect). Default: nothing to release."""
