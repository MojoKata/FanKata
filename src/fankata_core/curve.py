"""Curves: validation rules and monotone cubic (Fritsch–Carlson / PCHIP) evaluation.

The same evaluator draws the curve in the GUI and computes duty cycles in the
service, so what the user sees is exactly what the fans get.
"""

from __future__ import annotations

import bisect
from typing import Iterable, Sequence

FLOOR = 20.0          # minimum speed % unless a curve allows zero
Y_MIN, Y_MAX = 0.0, 100.0
X_MIN, X_MAX = 0.0, 100.0
MIN_POINTS = 2

Point = Sequence[float]


def _sign(v: float) -> int:
    return (v > 0) - (v < 0)


def _end_slope(h0: float, h1: float, d0: float, d1: float) -> float:
    v = ((2 * h0 + h1) * d0 - h0 * d1) / (h0 + h1)
    if _sign(v) != _sign(d0):
        return 0.0
    if _sign(d0) != _sign(d1) and abs(v) > abs(3 * d0):
        return 3 * d0
    return v


def _slopes(xs: list[float], ys: list[float]) -> list[float]:
    n = len(xs)
    h = [xs[i + 1] - xs[i] for i in range(n - 1)]
    d = [(ys[i + 1] - ys[i]) / h[i] for i in range(n - 1)]
    if n == 2:
        return [d[0], d[0]]
    m = [0.0] * n
    for i in range(1, n - 1):
        if d[i - 1] * d[i] <= 0:
            m[i] = 0.0
        else:
            w1, w2 = 2 * h[i] + h[i - 1], h[i] + 2 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i])
    m[0] = _end_slope(h[0], h[1], d[0], d[1])
    m[-1] = _end_slope(h[-1], h[-2], d[-1], d[-2])
    return m


class Interpolator:
    """Evaluates a curve at any x. Points must already satisfy the curve rules."""

    def __init__(self, points: Iterable[Point]):
        pts = sorted((float(p[0]), float(p[1])) for p in points)
        if len(pts) < MIN_POINTS:
            raise ValueError("a curve needs at least two points")
        self.xs = [p[0] for p in pts]
        self.ys = [p[1] for p in pts]
        self.m = _slopes(self.xs, self.ys)

    def __call__(self, x: float) -> float:
        xs, ys, m = self.xs, self.ys, self.m
        if x <= xs[0]:
            return ys[0]
        if x >= xs[-1]:
            return ys[-1]
        i = bisect.bisect_right(xs, x) - 1
        h = xs[i + 1] - xs[i]
        t = (x - xs[i]) / h
        t2, t3 = t * t, t * t * t
        y = ((2 * t3 - 3 * t2 + 1) * ys[i] + (t3 - 2 * t2 + t) * h * m[i]
             + (-2 * t3 + 3 * t2) * ys[i + 1] + (t3 - t2) * h * m[i + 1])
        return min(Y_MAX, max(Y_MIN, y))


def evaluate(points: Iterable[Point], x: float) -> float:
    return Interpolator(points)(x)


def sample(points: Iterable[Point], x0: float = X_MIN, x1: float = X_MAX, step: float = 0.5) -> list[float]:
    """y values from x0 to x1 inclusive, for drawing."""
    f = Interpolator(points)
    n = int(round((x1 - x0) / step))
    return [f(x0 + i * step) for i in range(n + 1)]


def _fmt(v: float) -> str:
    return f"{v:g}"


def floor_for(allow_zero: bool) -> float:
    return Y_MIN if allow_zero else FLOOR


def point_errors(points: Sequence[Point], allow_zero: bool) -> list[tuple[int | None, str]]:
    """Every rule violation, as (point index or None, message)."""
    errs: list[tuple[int | None, str]] = []
    if len(points) < MIN_POINTS:
        errs.append((None, "A curve needs at least two points."))
    floor = floor_for(allow_zero)
    for i, (x, y) in enumerate(points):
        if not (X_MIN <= x <= X_MAX):
            errs.append((i, f"Temperature {_fmt(x)} °C is outside {_fmt(X_MIN)}–{_fmt(X_MAX)} °C."))
        if not (Y_MIN <= y <= Y_MAX):
            errs.append((i, f"Speed {_fmt(y)} % is outside 0–100 %."))
        elif y < floor:
            errs.append((i, f"Speed at {_fmt(x)} °C can’t be below {_fmt(floor)} % unless Allow zero is on."))
        if i:
            px, py = points[i - 1]
            if x <= px:
                if x == px:
                    errs.append((i, f"Two points share {_fmt(x)} °C; temperatures must be unique."))
                else:
                    errs.append((i, "Points must be in order of increasing temperature."))
            elif y < py:
                errs.append((i, f"Speed at {_fmt(x)} °C can’t be lower than {_fmt(py)} % (the speed at {_fmt(px)} °C)."))
    return errs


def add_point_reason(points: Sequence[Point], x: float, y: float, allow_zero: bool) -> str | None:
    """Why (x, y) can't be added, or None if it can."""
    if not (X_MIN <= x <= X_MAX):
        return f"Temperature must be within {_fmt(X_MIN)}–{_fmt(X_MAX)} °C."
    floor = floor_for(allow_zero)
    if y < floor:
        return f"Speed can’t be below {_fmt(floor)} % unless Allow zero is on."
    if y > Y_MAX:
        return "Speed can’t exceed 100 %."
    for px, py in points:
        if px == x:
            return f"There is already a point at {_fmt(x)} °C."
    prev = [p for p in points if p[0] < x]
    nxt = [p for p in points if p[0] > x]
    if prev and y < prev[-1][1]:
        return f"Speed must be at least {_fmt(prev[-1][1])} % (the speed at {_fmt(prev[-1][0])} °C)."
    if nxt and y > nxt[0][1]:
        return f"Speed must be at most {_fmt(nxt[0][1])} % (the speed at {_fmt(nxt[0][0])} °C)."
    return None


def valid_band(points: Sequence[Point], x: float, allow_zero: bool) -> tuple[float, float]:
    """The range of speeds a new point at x may take."""
    prev = [p for p in points if p[0] < x]
    nxt = [p for p in points if p[0] > x]
    lo = max(prev[-1][1] if prev else Y_MIN, floor_for(allow_zero))
    hi = nxt[0][1] if nxt else Y_MAX
    return lo, hi


def raise_to_floor(points: Sequence[Point]) -> list[list[float]]:
    """Used when Allow zero is turned off. Order is preserved, so the curve stays non-decreasing."""
    return [[x, max(y, FLOOR)] for x, y in points]
