"""€STR (discounting) and EURIBOR 6M (projection) curves: unknowns x_k = ln P(T_k) at the pillars, log-linear
interpolation, global Newton.

The Jacobian is analytic: the curve returns `Dual` numbers (value + gradient with respect to the x_k), propagated
exactly through the instrument formulas (forward-mode automatic differentiation).
"""
import math
from datetime import date

import numpy as np

from ratecurves import dates as dt
from ratecurves.instruments import IRS, OIS, Deposit


class Dual:
    """Dual number v + g·ε: exact first-order arithmetic, g = gradient (numpy vector)."""
    __slots__ = ("v", "g")

    def __init__(self, v, g):
        self.v, self.g = v, g

    @staticmethod
    def _c(o):
        return o if isinstance(o, Dual) else Dual(o, 0.0)

    def __add__(self, o):
        o = self._c(o)
        return Dual(self.v + o.v, self.g + o.g)

    __radd__ = __add__

    def __sub__(self, o):
        o = self._c(o)
        return Dual(self.v - o.v, self.g - o.g)

    def __rsub__(self, o):
        return self._c(o) - self

    def __mul__(self, o):
        o = self._c(o)
        return Dual(self.v * o.v, self.g * o.v + o.g * self.v)

    __rmul__ = __mul__

    def __truediv__(self, o):
        o = self._c(o)
        return Dual(self.v / o.v, (self.g * o.v - o.g * self.v) / (o.v * o.v))

    def __rtruediv__(self, o):
        return self._c(o) / self

    def __neg__(self):
        return Dual(-self.v, -self.g)


class Curve:
    """ln P linear in t = ACT/365F between (0, 0) and the pillars; constant forward beyond the last one."""

    def __init__(self, day: date, pillars: list[date], x):
        self.day, self.pillars = day, list(pillars)
        self.x = np.asarray(x, dtype=float)
        self.t = np.array([0.0] + [dt.year_fraction(day, d, "ACT/365F") for d in pillars])

    def _weights(self, d: date):
        """(i, w): ln P(d) = (1 - w)·X[i] + w·X[i+1], X = [0, x_1, ..., x_n]."""
        t = dt.year_fraction(self.day, d, "ACT/365F")
        if t < 0:
            raise ValueError(f"date {d} is before the curve date {self.day}")
        i = min(int(np.searchsorted(self.t, t, side="right")) - 1, len(self.t) - 2)
        return i, (t - self.t[i]) / (self.t[i + 1] - self.t[i])

    def ln_p(self, d: date) -> float:
        i, w = self._weights(d)
        X = np.r_[0.0, self.x]
        return (1 - w) * X[i] + w * X[i + 1]

    def P(self, d: date) -> float:
        return math.exp(self.ln_p(d))

    def P_dual(self, d: date) -> Dual:
        i, w = self._weights(d)
        X = np.r_[0.0, self.x]
        p = math.exp((1 - w) * X[i] + w * X[i + 1])
        g = np.zeros(len(self.x))
        if i > 0:
            g[i - 1] = (1 - w) * p
        g[i] = w * p
        return Dual(p, g)


def _v(z):
    return z.v if isinstance(z, Dual) else z


def _exp(z):
    if isinstance(z, Dual):
        e = math.exp(z.v)
        return Dual(e, e * z.g)
    return math.exp(z)


def _cube(z):
    return z * z * z


def primitive_g(g0, g1, x):
    """G(x) = ∫_0^x g, g = gap between the instantaneous forward and the discrete forward on an interval mapped to [0, 1].

    Hagan & West (2006), monotone convex method: g(0) = g0, g(1) = g1, G(1) = 0 (∫f is preserved); four regions
    depending on (g0, g1). Works on floats or `Dual` numbers (branches are chosen on the values).
    """
    a, b = _v(g0), _v(g1)
    if a == 0 and b == 0:
        return 0.0
    if (a < 0 and -a / 2 <= b <= -2 * a) or (a > 0 and -a / 2 >= b >= -2 * a):  # (i) quadratic
        return g0 * (x - 2 * x * x + x * x * x) + g1 * (x * x * x - x * x)
    if (a < 0 and b > -2 * a) or (a > 0 and b < -2 * a):  # (ii) flat then quadratic
        eta = (g1 + 2 * g0) / (g1 - g0)
        if x <= _v(eta):
            return g0 * x
        return g0 * x + (g1 - g0) * _cube(x - eta) / (3 * (1 - eta) * (1 - eta))
    if (a > 0 and 0 > b > -a / 2) or (a < 0 and 0 < b < -a / 2):  # (iii) quadratic then flat
        eta = 3 * g1 / (g1 - g0)
        if x < _v(eta):
            return g1 * x + (g0 - g1) * (_cube(eta) - _cube(eta - x)) / (3 * eta * eta)
        return g1 * x + (g0 - g1) * eta / 3
    eta = g1 / (g1 + g0)  # (iv) g0 and g1 of the same sign: two quadratics joined at the minimum A
    A = -g0 * g1 / (g0 + g1)
    if x <= _v(eta):
        return A * x + (g0 - A) * (_cube(eta) - _cube(eta - x)) / (3 * eta * eta)
    return A * x + (g0 - A) * eta / 3 + (g1 - A) * _cube(x - eta) / (3 * (1 - eta) * (1 - eta))


class CurveHW(Curve):
    """Hagan-West monotone convex on the same unknowns x_k = ln P(T_k): continuous instantaneous forward, ∫f preserved
    on each interval (the DFs at the pillars are exactly exp(x_k)). Beyond the last pillar: last discrete forward
    extended, like log-linear and QuantLib (the instantaneous forward jumps there from f_n to fd_n).

    shortcut: without the paper's positivity constraint (useless with positive rates, harmful with negative rates),
    add it as an option if a negative forward appears on positive quotes. Not local: x_k affects the neighbouring
    intervals through the forwards at the nodes.
    """

    def __init__(self, day: date, pillars: list[date], x):
        super().__init__(day, pillars, x)
        e = np.eye(len(self.x))
        self._float = self._nodes([0.0] + list(self.x))
        self._dual = self._nodes([0.0] + [Dual(v, e[k]) for k, v in enumerate(self.x)])

    def _nodes(self, X):
        """(X, discrete forwards fd_i on ]t_{i-1}, t_i], instantaneous forwards f_i at the nodes)."""
        t, n = self.t, len(self.t) - 1
        fd = [None] + [(X[i - 1] - X[i]) / (t[i] - t[i - 1]) for i in range(1, n + 1)]
        f = [None] * (n + 1)
        for i in range(1, n):
            f[i] = ((t[i] - t[i - 1]) * fd[i + 1] + (t[i + 1] - t[i]) * fd[i]) / (t[i + 1] - t[i - 1])
        if n == 1:
            f[0] = f[1] = fd[1]
        else:
            f[0] = fd[1] - 0.5 * (f[1] - fd[1])
            f[n] = fd[n] - 0.5 * (f[n - 1] - fd[n])
        return X, fd, f

    def _ln(self, d: date, nodes):
        X, fd, f = nodes
        t = dt.year_fraction(self.day, d, "ACT/365F")
        if t < 0:
            raise ValueError(f"date {d} is before the curve date {self.day}")
        n = len(self.t) - 1
        if t >= self.t[n]:
            return X[n] - fd[n] * (t - self.t[n])
        i = int(np.searchsorted(self.t, t, side="right"))  # t in [t_{i-1}, t_i[
        h = self.t[i] - self.t[i - 1]
        x = (t - self.t[i - 1]) / h
        return X[i - 1] - fd[i] * (t - self.t[i - 1]) - h * primitive_g(f[i - 1] - fd[i], f[i] - fd[i], x)

    def ln_p(self, d: date) -> float:
        return self._ln(d, self._float)

    def P_dual(self, d: date) -> Dual:
        return _exp(self._ln(d, self._dual))


def newton(day: date, instruments: list, quotes, discount=None, cls=Curve, tol: float = 1e-13,
           max_iter: int = 30) -> Curve:
    """Solves rate_k(curve) = quote_k (decimal); one pillar per instrument (last relevant date).

    `discount`: exogenous discount curve (P(date) as float) passed to the instruments; None = the curve itself.
    `cls`: Curve (log-linear) or CurveHW.

    Starts from log-linear: flat curve at each quote (Newton converges in ~4 iterations). Log-linear being local,
    its solution is that of a sequential bootstrap; it is the starting point for the other classes.
    """
    pillars = [i.pillar for i in instruments]
    if any(a >= b for a, b in zip(pillars, pillars[1:])):
        raise ValueError("pillars not strictly increasing")
    q = np.asarray(quotes, dtype=float)
    if cls is Curve:
        x = -q * np.array([dt.year_fraction(day, d, "ACT/365F") for d in pillars])
    else:
        x = newton(day, instruments, quotes, discount, Curve, tol, max_iter).x
    c = cls(day, pillars, x)
    for _ in range(max_iter):
        duals = [i.rate(c.P_dual, discount) if discount else i.rate(c.P_dual) for i in instruments]
        residuals = np.array([d.v for d in duals]) - q
        c.jacobian = np.array([d.g for d in duals])  # dR/dx, reused for the buckets
        c.residuals = residuals
        if np.max(np.abs(residuals)) < tol:
            return c
        c = cls(day, pillars, c.x - np.linalg.solve(c.jacobian, residuals))
    raise RuntimeError(f"Newton did not converge: max|R| = {np.max(np.abs(residuals)):.2e}")


def estr_curve(day: date, ois_quotes: dict, cls=Curve) -> Curve:
    """€STR curve of the day from OIS rates (in %, {tenor: rate})."""
    spot = dt.add_business_days(day, 2)
    instruments = sorted((OIS(spot, t) for t in ois_quotes), key=lambda i: i.pillar)
    c = newton(day, instruments, [ois_quotes[i.tenor] / 100 for i in instruments], cls=cls)
    c.instruments = instruments
    c.quotes = [ois_quotes[i.tenor] / 100 for i in instruments]
    return c


def instrument_6m(spot: date, key: str):
    """6M calibration instrument from its quote key ("DEPOSIT 6M", "FRA 1x7", "IRS 10Y")."""
    typ, tenor = key.split()
    return Deposit(spot) if typ == "DEPOSIT" else Deposit(spot, int(tenor.split("x")[0])) if typ == "FRA" else IRS(spot, tenor)


def euribor6m_curve(day: date, quotes: dict, estr: Curve, cls=Curve) -> Curve:
    """EURIBOR 6M projection curve, discounted on the €STR curve.

    `quotes` in %: {"DEPOSIT 6M": r, "FRA 1x7": r, ..., "IRS 2Y": r, ...}. An IRS whose pillar falls within 5 days of
    a deposit / FRA pillar is dropped (in practice the 2Y IRS, same maturity as the 18x24 FRA).
    """
    spot = dt.add_business_days(day, 2)
    candidates = []
    for key, v in quotes.items():
        i = instrument_6m(spot, key)
        candidates.append((i.pillar, key.startswith("IRS"), i, v))
    kept = []
    for pillar, _, i, v in sorted(candidates, key=lambda x: x[1]):  # deposits / FRAs first: they win at close pillars
        # "equal" pillar within 5 days: depending on the day, the ends of the 18x24 FRA and the 2Y IRS differ by one day
        if all(abs((pillar - p).days) > 5 for p, _, _ in kept):
            kept.append((pillar, i, v))
    kept.sort(key=lambda x: x[0])
    instruments, q = [i for _, i, _ in kept], [v / 100 for _, _, v in kept]
    c = newton(day, instruments, q, discount=estr.P, cls=cls)
    c.instruments = instruments
    c.quotes = q  # decimal, in the order of the kept instruments
    return c
