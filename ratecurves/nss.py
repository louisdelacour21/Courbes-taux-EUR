"""Nelson-Siegel-Svensson fit: smoothing and level / slope / curvature reading, never pricing.

y(τ) = β0 + β1 L(τ/λ1) + β2 [L(τ/λ1) − e^{−τ/λ1}] + β3 [L(τ/λ2) − e^{−τ/λ2}],  L(u) = (1 − e^{−u})/u,
continuously compounded zero rate (decimal), τ in years ACT/365F.
β by ordinary least squares at fixed (λ1, λ2); (λ1, λ2) by grid then least_squares ("profiled" β).

Identification: λ2 ≥ 2 λ1 (ECB ordering: τ1 ~ 3 years, τ2 ~ 13 years) and λ ≤ 30 years. Without these constraints the
optimum often drifts to λ1 ≈ λ2 (the two humps become collinear, β2 ≈ −β3 ~ ±1e3) or to λ → ∞ (slope and curvature
collinear with the level): same RMSE, meaningless parameters that are unstable from one day to the next.
"""
import numpy as np
from scipy.optimize import least_squares

GRID = np.geomspace(0.1, 30.0, 16)
L_MIN, L_MAX = 0.1, 30.0


def loadings(t, l1, l2):
    """(n, 4) matrix of loadings [1, L1, L1 − e1, L2 − e2]; limit τ → 0: [1, 1, 0, 0]."""
    t = np.maximum(np.asarray(t, dtype=float), 1e-10)
    u1, u2 = t / l1, t / l2
    L1, L2 = -np.expm1(-u1) / u1, -np.expm1(-u2) / u2
    return np.column_stack([np.ones_like(t), L1, L1 - np.exp(-u1), L2 - np.exp(-u2)])


def zero(t, beta, l1, l2):
    return loadings(t, l1, l2) @ np.asarray(beta)


def _beta(t, y, l1, l2):
    return np.linalg.lstsq(loadings(t, l1, l2), y, rcond=None)[0]


def _lambdas(z):
    """z = (ln λ1, s): λ2 = 2 λ1 + s (λ_max − 2 λ1), s ∈ [0, 1], i.e. 2 λ1 ≤ λ2 ≤ λ_max."""
    l1 = np.exp(z[0])
    return l1, 2 * l1 + z[1] * (L_MAX - 2 * l1)


def _residuals(z, t, y):
    l1, l2 = _lambdas(z)
    return loadings(t, l1, l2) @ _beta(t, y, l1, l2) - y


class NSS:
    def __init__(self, beta, l1, l2, rmse):
        self.beta, self.l1, self.l2, self.rmse = np.asarray(beta), l1, l2, rmse

    def zero(self, t):
        return zero(t, self.beta, self.l1, self.l2)

    @property
    def level(self):  # infinite-maturity zero rate
        return self.beta[0]

    @property
    def slope(self):  # long − short: y(∞) − y(0) = −β1
        return -self.beta[1]


def fit(t, y) -> NSS:
    """Fits NSS to the zero rates y (decimal) at maturities t (years)."""
    t, y = np.asarray(t, dtype=float), np.asarray(y, dtype=float)
    grid = [(np.log(a), (b - 2 * a) / (L_MAX - 2 * a)) for a in GRID for b in GRID if 2 * a <= b]
    start = min(grid, key=lambda z: np.sum(_residuals(z, t, y) ** 2))
    r = least_squares(_residuals, start, args=(t, y), bounds=([np.log(L_MIN), 0.0], [np.log(L_MAX / 2), 1.0]),
                      xtol=1e-15, ftol=1e-15, gtol=1e-15)
    l1, l2 = _lambdas(r.x)
    return NSS(_beta(t, y, l1, l2), l1, l2, float(np.sqrt(np.mean(r.fun ** 2))))


def fit_curve(curve) -> NSS:
    """NSS fitted to the bootstrapped zero rates of the curve, at its pillars."""
    t = curve.t[1:]
    return fit(t, -curve.x / t)
