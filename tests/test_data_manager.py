import numpy as np
import pytest

from core.data_manager import DataManager, Series


def test_series_grows_and_keeps_old_views():
    s = Series(capacity=4)
    s.extend(np.arange(3.0), np.arange(3.0) * 2)
    old_t, _ = s.view()
    s.extend(np.arange(3.0, 10.0), np.arange(3.0, 10.0) * 2)
    t, y = s.view()
    assert np.array_equal(t, np.arange(10.0)) and np.array_equal(y, t * 2)
    assert np.array_equal(old_t, [0, 1, 2])  # earlier view untouched by reallocation


def test_runs_and_latest():
    dm = DataManager()
    assert dm.latest("a") is None
    dm.start_run()
    dm.append("a", np.array([0.0, 1.0]), np.array([5.0, 6.0]))
    dm.stop_run()
    dm.append("a", np.array([2.0]), np.array([7.0]))  # after stop: dropped
    assert list(dm.latest("a")[1]) == [5.0, 6.0]
    dm.start_run()
    assert dm.latest("a") is None and len(dm.runs) == 2 and dm.runs[1].number == 2


def test_append_rejects_length_mismatch():
    dm = DataManager()
    dm.start_run()
    with pytest.raises(ValueError):
        dm.append("a", np.zeros(2), np.zeros(3))
