"""Curve interpolation for smooth yield curve plotting."""
import numpy as np
from scipy.interpolate import PchipInterpolator


def interpolate_curve(years: list, yields: list, num_points: int = 200) -> tuple:
    """PCHIP interpolation (monotone cubic, avoids overshoot). Returns (x, y) numpy arrays."""
    if len(years) < 2:
        return np.array(years), np.array(yields)
    x = np.array(years, dtype=float)
    y = np.array(yields, dtype=float)
    _, idx = np.unique(x, return_index=True)
    x, y = x[idx], y[idx]
    if len(x) < 2:
        return x, y
    order = np.argsort(x)
    x, y = x[order], y[order]
    try:
        cs = PchipInterpolator(x, y)
        xs = np.linspace(x[0], x[-1], num_points)
        return xs, cs(xs)
    except Exception:
        xs = np.linspace(x[0], x[-1], num_points)
        return xs, np.interp(xs, x, y)
