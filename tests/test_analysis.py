import numpy as np
import pytest

from openpasco.analysis import numeric as nm

T = np.linspace(0, 10, 501)


def test_select_inclusive_and_empty():
    t, y = nm.select(T, T * 2, 1.0, 2.0)
    assert t[0] == 1.0 and t[-1] == 2.0 and len(t) == 51
    assert len(nm.select(T, T, 20, 30)[0]) == 0


def test_statistics():
    s = nm.statistics(np.array([0., 1, 2, 3]), np.array([2., 4, 4, 6]))
    assert (s.n, s.mean, s.minimum, s.maximum, s.t_min, s.t_max) == (4, 4.0, 2.0, 6.0, 0.0, 3.0)
    assert s.std == pytest.approx(np.std([2, 4, 4, 6], ddof=1))
    assert np.isnan(nm.statistics(np.array([0.]), np.array([1.])).std)
    with pytest.raises(ValueError):
        nm.statistics(np.array([]), np.array([]))


def test_linear_fit_recovers_params():
    rng = np.random.default_rng(1)
    f = nm.fit("선형", T, 3 * T - 2 + rng.normal(0, 0.1, T.size))
    assert f.params["m"] == pytest.approx(3, abs=0.02) and f.params["b"] == pytest.approx(-2, abs=0.1)
    assert f.r2 > 0.99 and "R²" in f.summary()
    assert f.predict(np.array([1.0]))[0] == pytest.approx(1, abs=0.2)


def test_sine_and_exp_fit():
    f = nm.fit("사인", T, 2 * np.sin(2 * np.pi * 0.5 * T + 0.3) + 1)
    assert abs(f.params["w"]) == pytest.approx(np.pi, rel=1e-3) and f.r2 > 0.999
    g = nm.fit("지수", T, 2 * np.exp(-0.4 * T) + 1)
    assert g.params["k"] == pytest.approx(-0.4, rel=1e-3) and g.params["c"] == pytest.approx(1, abs=1e-3)


def test_fit_errors():
    with pytest.raises(ValueError, match="최소"):
        nm.fit("2차", T[:3], T[:3])


def test_derivative_and_integral_inverse():
    d = nm.derivative(T, T**2)
    assert d[250] == pytest.approx(2 * T[250], rel=1e-9) and d[0] == pytest.approx(0, abs=0.02)
    i = nm.integral(T, np.cos(T))
    assert i[0] == 0 and i[-1] == pytest.approx(np.sin(10), abs=1e-3)
    with pytest.raises(ValueError):
        nm.derivative(np.array([1.0]), np.array([1.0]))


def test_auto_analyze_picks_linear_for_a_line():
    from openpasco.analysis.numeric import auto_analyze
    t = np.linspace(0, 10, 50)
    a = auto_analyze(t, 2 * t + 1)
    assert a.fit.name == "선형" and a.trend == "증가" and a.peaks == []


def test_auto_analyze_finds_sine_and_peaks():
    from openpasco.analysis.numeric import auto_analyze
    t = np.linspace(0, 10, 400)
    a = auto_analyze(t, 3 * np.sin(2 * np.pi * 0.5 * t))
    assert a.fit.name == "사인" and len(a.peaks) == 5 and a.trend == "일정"


def test_auto_analyze_few_points_does_not_crash():
    from openpasco.analysis.numeric import auto_analyze
    a = auto_analyze([0, 1], [1, 1])
    assert a.fit is None and "n=2" in a.summary()
