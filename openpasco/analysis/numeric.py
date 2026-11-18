"""Pure-numpy/scipy analysis of (t, y) series. No Qt, no hardware."""
from dataclasses import dataclass
from typing import Callable

import numpy as np
from scipy.optimize import curve_fit
from scipy.integrate import cumulative_trapezoid


def select(t: np.ndarray, y: np.ndarray, lo: float, hi: float) -> tuple[np.ndarray, np.ndarray]:
    """Samples with lo <= t <= hi (t is sorted, so this is a slice)."""
    i, j = np.searchsorted(t, lo, side="left"), np.searchsorted(t, hi, side="right")
    return t[i:j], y[i:j]


@dataclass(frozen=True)
class Stats:
    n: int
    mean: float
    std: float  # sample standard deviation (ddof=1); NaN for n < 2
    minimum: float
    maximum: float
    t_min: float
    t_max: float


def statistics(t, y) -> Stats:
    if len(y) == 0:
        raise ValueError("데이터가 없습니다")
    return Stats(len(y), float(np.mean(y)), float(np.std(y, ddof=1)) if len(y) > 1 else float("nan"),
                 float(np.min(y)), float(np.max(y)), float(t[np.argmin(y)]), float(t[np.argmax(y)]))


@dataclass(frozen=True)
class Fit:
    name: str
    params: dict[str, float]
    errors: dict[str, float]  # 1-sigma standard errors
    r2: float
    predict: Callable[[np.ndarray], np.ndarray]

    def summary(self) -> str:
        p = ", ".join(f"{k}={v:.4g}±{self.errors[k]:.2g}" for k, v in self.params.items())
        return f"{self.name}: {p}, R²={self.r2:.4f}"


def _r2(y, yhat):
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    return float(1 - np.sum((y - yhat) ** 2) / ss_tot) if ss_tot > 0 else 1.0


# name -> (function, parameter names, initial-guess function)
MODELS = {
    "선형": (lambda x, m, b: m * x + b, ["m", "b"], None),
    "2차": (lambda x, a, b, c: a * x**2 + b * x + c, ["a", "b", "c"], None),
    "사인": (lambda x, A, w, p, c: A * np.sin(w * x + p) + c, ["A", "w", "p", "c"], "sine"),
    "지수": (lambda x, A, k, c: A * np.exp(k * x) + c, ["A", "k", "c"], "exp"),  # tries both signs of k
}


def _sine_guess(t, y):
    c = float(np.mean(y))
    f = np.abs(np.fft.rfft(y - c))
    f[0] = 0
    freqs = np.fft.rfftfreq(len(t), (t[-1] - t[0]) / (len(t) - 1))
    w = 2 * np.pi * freqs[int(np.argmax(f))]
    return [float((y.max() - y.min()) / 2), float(w), 0.0, c]


def fit(model: str, t, y) -> Fit:
    """Least-squares fit. Raises ValueError when the data cannot support the model."""
    func, names, guess = MODELS[model]
    t, y = np.asarray(t, float), np.asarray(y, float)
    if len(t) < len(names) + 1:
        raise ValueError(f"'{model}' 피팅에는 최소 {len(names) + 1}개의 점이 필요합니다")
    span = max(t[-1] - t[0], 1e-9)
    if guess == "sine":
        starts = [_sine_guess(t, y)]
    elif guess == "exp":  # decay and growth need different starting points
        starts = [[float(y[0] - y[-1]) or 1.0, -3 / span, float(y[-1])],
                  [float(y[-1] - y[0]) or 1.0, 3 / span, float(y[0])]]
    else:
        starts = [None]
    best = None
    for p0 in starts:
        try:
            popt, pcov = curve_fit(func, t, y, p0=p0, maxfev=20000)
        except (RuntimeError, ValueError):
            continue
        sse = float(np.sum((y - func(t, *popt)) ** 2))
        if best is None or sse < best[0]:
            best = (sse, popt, pcov)
    if best is None:
        raise ValueError(f"'{model}' 피팅이 수렴하지 않았습니다")
    _, popt, pcov = best
    err = np.sqrt(np.diag(pcov)) if np.all(np.isfinite(pcov)) else np.full(len(names), np.nan)
    return Fit(model, dict(zip(names, map(float, popt))), dict(zip(names, map(float, err))),
               _r2(y, func(t, *popt)), lambda x, p=popt: func(np.asarray(x, float), *p))


def derivative(t, y) -> np.ndarray:
    """dy/dt via central differences (one-sided at the ends); handles uneven t."""
    if len(t) < 2:
        raise ValueError("미분에는 최소 2개의 점이 필요합니다")
    return np.gradient(y, t)


def integral(t, y) -> np.ndarray:
    """Cumulative trapezoid integral, starting at 0."""
    return cumulative_trapezoid(y, t, initial=0.0)
