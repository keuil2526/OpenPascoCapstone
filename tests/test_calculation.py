import numpy as np
import pytest

from openpasco.core.calculation import CalcError, evaluate, parse

T = np.arange(5) * 0.5
DATA = {"위치": (T, np.array([0., 1, 2, 3, 4])), "force": (T, np.array([2., 2, 2, 2, 2])),
        "slow": (np.array([0., 1, 2]), np.array([10., 20, 30]))}
res = DATA.get


def calc(expr):
    return evaluate(expr, res)


def test_arithmetic_and_refs():
    t, y = calc("[위치] * 2 + [force] ** 2 - 1")
    assert np.array_equal(t, T) and list(y) == [3, 5, 7, 9, 11]
    assert parse("[a] + [b] * [a]")[1] == ["a", "b"]


def test_functions_constants_time():
    assert calc("sqrt([위치]) * 0 + pi")[1][0] == pytest.approx(np.pi)
    assert list(calc("[위치] * 0 + t")[1]) == list(T)
    assert calc("-[위치] + +1")[1][0] == 1 and calc("abs(-[force])")[1][0] == 2


def test_resample_other_time_base():
    t, y = calc("[force] + [slow]")  # slow covers t in [0, 2]; base t goes to 2.0 -> in range
    assert y[0] == 12 and y[1] == pytest.approx(2 + 10 + 5)  # interpolated at t=0.5
    t, y = evaluate("[slow] + [force]", res)  # base = slow, force interpolated
    assert len(t) == 3 and list(y) == [12, 22, 32]
    far = dict(DATA, late=(np.array([10., 11]), np.array([1., 1])))
    assert np.isnan(evaluate("[force] + [late]", far.get)[1]).all()


def test_math_errors_do_not_raise():
    y = calc("1 / ([위치] - [위치]) ")[1]
    assert np.isinf(y).all() or np.isnan(y).any()
    assert np.isnan(calc("sqrt(0 - [force])")[1]).all()


@pytest.mark.parametrize("bad", [
    "", "   ", "[위치] +", "__import__('os')", "[위치].real", "open('x')", "lambda: 1", "[a][0]",
    "[위치] if 1 else 2", "x", "sin()", "sin([위치], 2)", "foo([위치])", "'abc'", "[위치] < 2",
    "[위치] _v0", "(" * 300 + "[위치]" + ")" * 300, "[위치]" * 600, "True", "1 + [force]; 2",
])
def test_rejects_unsafe_or_invalid(bad):
    with pytest.raises(CalcError):
        calc(bad)


def test_requires_a_measurement_and_data():
    with pytest.raises(CalcError, match="하나 이상"):
        calc("1 + 2")
    with pytest.raises(CalcError, match="없습니다"):
        calc("[없는 측정값] + 1")
    with pytest.raises(CalcError, match="없습니다"):
        evaluate("[위치]", lambda n: (np.empty(0), np.empty(0)))
