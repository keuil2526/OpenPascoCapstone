import threading
import time

import numpy as np

from openpasco.hardware import simulated


def test_scan_returns_sensors_with_measurements():
    sensors = simulated.scan()
    assert len(sensors) == 2 and all(s.measurements for s in sensors)


def test_streams_ideal_timestamps_and_stops_cleanly():
    sensor = simulated.scan()[0]
    chunks, lock = [], threading.Lock()

    def on_samples(sid, t, values):
        with lock:
            chunks.append((sid, t, values))

    sensor.start(200, on_samples)
    time.sleep(0.25)
    sensor.stop()
    n_at_stop = len(chunks)
    time.sleep(0.05)
    assert len(chunks) == n_at_stop  # no callbacks after stop() returns

    t = np.concatenate([c[1] for c in chunks])
    assert 30 < len(t) < 70
    assert np.allclose(np.diff(t), 1 / 200) and t[0] == 0
    for _, ct, values in chunks:
        assert set(values) == {"position", "velocity"}
        assert all(len(v) == len(ct) for v in values.values())
    sensor.start(10, on_samples)  # restartable
    sensor.stop()
