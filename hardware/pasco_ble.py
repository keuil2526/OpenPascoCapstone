"""PASCO wireless (BLE) sensors through PASCO's own `pasco` Python library.

The library is optional and not bundled (personal/educational licence, see requirements-pasco.txt).
We only call its public API; no code from it is copied here.
UNTESTED WITH REAL HARDWARE: written against the library's documented API and verified with fakes.
"""
import threading
import time

import numpy as np

from hardware.base import Measurement, SampleCallback, Sensor

try:
    from pasco import PASCOBLEDevice
except ImportError:  # optional dependency
    PASCOBLEDevice = None

MISSING_LIB = "pasco 라이브러리가 없어 BLE 센서는 검색하지 않았습니다 (pip install -r requirements-pasco.txt)"
DEFAULT_RANGE = (0.0, 10.0)  # shortcut: real display ranges are not read from the device yet


class PascoBleSensor(Sensor):
    """One connected PASCO BLE device. The library only offers one-shot reads, so we poll."""

    def __init__(self, device, name: str | None, address: str):
        self._dev = device
        self.id, self.name = f"pasco:{address}", name or address
        self.measurements = []
        for m in device.get_measurement_list():
            try:
                unit = device.get_measurement_unit(m) or ""
            except Exception:  # unit lookup is cosmetic
                unit = ""
            self.measurements.append(Measurement(m, m, str(unit), *DEFAULT_RANGE))
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self, rate_hz: float, on_samples: SampleCallback) -> None:
        if self._thread:
            raise RuntimeError(f"{self.name} already running")
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, args=(rate_hz, on_samples),
                                        name=f"ble-{self.id}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._thread:
            self._stop.set()
            self._thread.join()
            self._thread = None

    def close(self) -> None:
        self.stop()
        try:
            self._dev.disconnect()
        except Exception:
            pass  # already gone

    def _run(self, rate_hz, on_samples):
        names = [m.id for m in self.measurements]
        period, t0 = 1.0 / rate_hz, time.monotonic()
        due = t0
        while not self._stop.is_set():
            try:
                vals = self._dev.read_data_list(names)
            except Exception as e:  # connection lost, device off, ...
                if self.on_error:
                    self.on_error(f"{self.name}: {e or type(e).__name__}")
                return
            # shortcut: timestamps are host receive times (jitter ~ link latency), not sensor clock
            t = np.array([time.monotonic() - t0])
            on_samples(self.id, t, {n: np.array([np.nan if vals.get(n) is None else float(vals[n])])
                                    for n in names})
            due += period
            delay = due - time.monotonic()
            if delay > 0:
                self._stop.wait(delay)
            else:
                due = time.monotonic()  # link slower than requested: go as fast as it allows


def scan(factory=None) -> tuple[list[Sensor], list[str]]:
    """Find and connect to PASCO BLE devices. Blocks for several seconds. Returns (sensors, warnings)."""
    factory = factory or PASCOBLEDevice
    if factory is None:
        return [], [MISSING_LIB]
    try:
        found = factory().scan()
    except Exception as e:
        # the library re-raises a bare BLEScanFailed; the real cause is the implicit context
        cause = e.__context__ or e
        hint = (" — BlueZ가 '이미 진행 중'이라고 응답했습니다. 블루투스를 껐다 켜 보세요"
                if "InProgress" in str(cause) else "")
        return [], [f"BLE 검색 실패: {cause}{hint}"]
    sensors, warnings = [], []
    for ble in found:
        dev = factory()
        try:
            dev.connect(ble)
            sensors.append(PascoBleSensor(dev, ble.name, ble.address))
        except Exception as e:
            warnings.append(f"{ble.name or ble.address} 연결 실패: {e or type(e).__name__}")
            try:
                dev.disconnect()
            except Exception:
                pass
    return sensors, warnings
