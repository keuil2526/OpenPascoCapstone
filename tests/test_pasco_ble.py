import threading
import time
from types import SimpleNamespace

import numpy as np

from openpasco.hardware import pasco_ble


class FakeDevice:
    """Stands in for pasco.PASCOBLEDevice."""

    def __init__(self, found=(), fail_connect=False, fail_after=None):
        self.found, self.fail_connect, self.fail_after = list(found), fail_connect, fail_after
        self.reads, self.disconnected = 0, False

    def scan(self):
        return self.found

    def connect(self, ble):
        if self.fail_connect:
            raise RuntimeError("Could not connect")

    def disconnect(self):
        self.disconnected = True

    def get_measurement_list(self):
        return ["Temperature", "Force"]

    def get_measurement_unit(self, m):
        return {"Temperature": "°C"}.get(m)  # None for Force

    def read_data_list(self, names):
        self.reads += 1
        if self.fail_after is not None and self.reads > self.fail_after:
            raise ConnectionError("link lost")
        return {"Temperature": 21.5, "Force": None}


BLE = SimpleNamespace(name="Temp 123-456", address="AA:BB")


def collect(sensor, rate, seconds):
    got = []
    sensor.start(rate, lambda sid, t, v: got.append((sid, t, v)))
    time.sleep(seconds)
    sensor.stop()
    return got


def test_measurements_and_units():
    s = pasco_ble.PascoBleSensor(FakeDevice(), "Temp 123-456", "AA:BB")
    assert s.id == "pasco:AA:BB" and s.name == "Temp 123-456"
    assert [(m.id, m.unit) for m in s.measurements] == [("Temperature", "°C"), ("Force", "")]


def test_polls_and_maps_none_to_nan():
    s = pasco_ble.PascoBleSensor(FakeDevice(), None, "AA:BB")
    got = collect(s, 50, 0.3)
    assert s.name == "AA:BB" and 5 < len(got) < 25
    t = np.concatenate([g[1] for g in got])
    assert t[0] >= 0 and np.all(np.diff(t) > 0)
    assert got[0][2]["Temperature"][0] == 21.5 and np.isnan(got[0][2]["Force"][0])


def test_connection_loss_reports_error_and_stops():
    errors = []
    s = pasco_ble.PascoBleSensor(FakeDevice(fail_after=3), "Temp", "AA:BB")
    s.on_error = errors.append
    got = collect(s, 200, 0.3)
    assert len(got) == 3 and len(errors) == 1 and "link lost" in errors[0] and "Temp" in errors[0]


def test_close_disconnects_and_stops():
    dev = FakeDevice()
    s = pasco_ble.PascoBleSensor(dev, "Temp", "AA:BB")
    s.start(50, lambda *a: None)
    s.close()
    assert dev.disconnected and not s._thread
    s.close()  # idempotent


def test_scan_connects_found_devices_and_reports_failures():
    devices = iter([FakeDevice(found=[BLE, SimpleNamespace(name="Bad", address="CC")]),
                    FakeDevice(), FakeDevice(fail_connect=True)])
    sensors, warnings = pasco_ble.scan(lambda: next(devices))
    assert [s.name for s in sensors] == ["Temp 123-456"]
    assert len(warnings) == 1 and "Bad" in warnings[0] and "Could not connect" in warnings[0]


def test_scan_failure_and_missing_library(monkeypatch):
    class Boom(FakeDevice):
        def scan(self):
            raise RuntimeError("no adapter")
    sensors, warnings = pasco_ble.scan(Boom)
    assert sensors == [] and "no adapter" in warnings[0]

    class Wrapped(FakeDevice):  # the real library hides the cause behind a bare exception
        def scan(self):
            try:
                raise RuntimeError("[org.bluez.Error.InProgress] Operation already in progress")
            except Exception:
                raise Exception()
    _, warnings = pasco_ble.scan(Wrapped)
    assert "InProgress" in warnings[0] and "껐다 켜" in warnings[0]
    monkeypatch.setattr(pasco_ble, "PASCOBLEDevice", None)
    assert pasco_ble.scan() == ([], [pasco_ble.MISSING_LIB])


def test_sensor_threads_do_not_leak():
    before = threading.active_count()
    s = pasco_ble.PascoBleSensor(FakeDevice(), "T", "A")
    collect(s, 50, 0.1)
    assert threading.active_count() == before
