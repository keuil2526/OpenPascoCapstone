import numpy as np

from openpasco.core.conditions import Condition, Conditions, Gate


def test_gate_without_start_passes_through_and_flags_stop():
    g = Gate(Conditions(stop=Condition("measure", "s:x", ">", 5)))
    t, v = g.filter("s", np.array([0.0, 1.0]), {"x": np.array([1.0, 2.0])})
    assert list(t) == [0.0, 1.0] and not g.stop_hit
    g.filter("s", np.array([2.0]), {"x": np.array([6.0])})
    assert g.stop_hit


def test_gate_start_waits_then_zeroes_time():
    g = Gate(Conditions(start=Condition("measure", "s:x", ">", 5)))
    assert g.filter("s", np.array([0.0, 1.0]), {"x": np.array([1.0, 2.0])}) is None
    assert g.filter("other", np.array([1.5]), {"y": np.array([9.0])}) is None  # not triggered yet
    t, v = g.filter("s", np.array([2.0, 3.0, 4.0]), {"x": np.array([3.0, 7.0, 8.0])})
    assert g.triggered and list(t) == [0.0, 1.0] and list(v["x"]) == [7.0, 8.0]  # t0 = 3.0, first hit


def test_gate_trims_other_sensor_samples_before_trigger():
    g = Gate(Conditions(start=Condition("measure", "s:x", "<", 0)))
    g.filter("s", np.array([10.0]), {"x": np.array([-1.0])})
    t, v = g.filter("o", np.array([9.0, 10.0, 11.0]), {"y": np.array([1.0, 2.0, 3.0])})
    assert list(t) == [0.0, 1.0] and list(v["y"]) == [2.0, 3.0]


def test_nan_never_triggers():
    assert not Condition("measure", "s:x", ">", 0).met([np.nan]).any()
