"""Risk of a swap portfolio on both curves: buckets via the Jacobian, DV01, hedging, IRRBB scenarios.

Unknowns x = [x_€STR, x_6M]. The global Jacobian J = ∂R/∂x is block-triangular (the 6M curve depends on €STR through
discounting, not the reverse). Buckets: ∂V/∂q = (∂V/∂x) J⁻¹, in EUR per bp of quote.
"""
import math

import numpy as np

from ratecurves.curves import CurveHW, Dual, estr_curve, euribor6m_curve
from ratecurves.instruments import IRS, OIS

BP = 1e-4


def build(day, ois: dict, six: dict, cls=CurveHW):
    """(€STR curve, 6M curve) from quotes in % ({tenor: rate} and {"TYPE tenor": rate})."""
    estr = estr_curve(day, ois, cls)
    return estr, euribor6m_curve(day, six, estr, cls)


def key(i) -> str:
    """Quote label of a calibration instrument, in the format of the dictionaries of `build`."""
    if isinstance(i, OIS):
        return i.tenor
    if isinstance(i, IRS):
        return f"IRS {i.tenor}"
    return f"DEPOSIT {i.tenor}" if i.tenor == "6M" else f"FRA {i.tenor}"


def _embed(P_dual, start: int, n: int):
    """P returning Duals whose gradient is placed at position `start` of a vector of size n."""
    def P(d):
        z = P_dual(d)
        g = np.zeros(n)
        g[start:start + len(z.g)] = z.g
        return Dual(z.v, g)
    return P


def jacobian(estr, six):
    """(J, P6, Pd): global Jacobian and dual discount functions on x = [x_€STR, x_6M]."""
    nd, n = len(estr.x), len(estr.x) + len(six.x)
    Pd, P6 = _embed(estr.P_dual, 0, n), _embed(six.P_dual, nd, n)
    J = np.array([i.rate(Pd).g for i in estr.instruments] + [i.rate(P6, Pd).g for i in six.instruments])
    return J, P6, Pd


def labels(estr, six) -> list[str]:
    return [f"OIS {i.tenor}" for i in estr.instruments] + [key(i) for i in six.instruments]


def _grad(v, n):
    return v.g if isinstance(v, Dual) else np.zeros(n)  # matured swap: value 0, no gradient


def buckets(swaps, day, estr, six, fixing=None):
    """(value, buckets) of the portfolio: buckets[k] = ∂V/∂q_k in EUR per bp, in the order of `labels`."""
    J, P6, Pd = jacobian(estr, six)
    v = sum((s.value(day, P6, Pd, fixing) for s in swaps), Dual(0.0, np.zeros(len(J))))
    return v.v, np.linalg.solve(J.T, v.g) * BP


def dv01_zero(swaps, day, estr, six, fixing=None) -> float:
    """∂V for +1 bp on the zero rates (continuous, ACT/365F) of both curves: x_k → x_k − 1 bp · t_k.

    Exact to first order for both interpolations: the shock moves every forward by 1 bp.
    """
    _, P6, Pd = jacobian(estr, six)
    t = np.r_[estr.t[1:], six.t[1:]]
    v = sum((s.value(day, P6, Pd, fixing) for s in swaps), Dual(0.0, np.zeros(len(t))))
    return float(v.g @ (-BP * t))


def value(swaps, day, estr, six, fixing=None) -> float:
    return sum(s.value(day, six.P, estr.P, fixing) for s in swaps)


def hedge(day, estr, six, delta):
    """Notionals h of the calibration instruments (fixed-rate payers, at par) that cancel the buckets: h = −B⁻¹δ.

    B[k, j] = bucket k of a unit notional of instrument j. At par, B is diagonal (instrument j depends only on its
    own quote), equal to its annuity × 1 bp; it is computed without assuming it.
    """
    J, P6, Pd = jacobian(estr, six)
    q = estr.quotes + six.quotes
    G = []
    for i, k in zip(estr.instruments + six.instruments, q):
        rate = i.rate(Pd) if isinstance(i, OIS) else i.rate(P6, Pd)
        G.append(((rate - k) * i.annuity(Pd)).g)
    B = np.linalg.solve(J.T, np.array(G).T) * BP
    return -np.linalg.solve(B, delta), B


# IRRBB, BCBS 2016 (EUR): shocks in bp on zero rates, t in years
SHOCKS = {"parallel_up": 200.0, "parallel_down": -200.0, "short": 250.0, "long": 100.0}
SCENARIOS = ["parallel_up", "parallel_down", "short_up", "short_down", "steepener", "flattener"]


def shock_bp(scenario: str, t: float) -> float:
    short = SHOCKS["short"] * math.exp(-t / 4)
    long = SHOCKS["long"] * (1 - math.exp(-t / 4))
    return {"parallel_up": SHOCKS["parallel_up"], "parallel_down": SHOCKS["parallel_down"],
            "short_up": short, "short_down": -short,
            "steepener": -0.65 * short + 0.9 * long, "flattener": 0.8 * short - 0.6 * long}[scenario]


def floor_bp(t: float) -> float:
    """EBA post-shock floor: −150 bp overnight, +3 bp per year, up to 0."""
    return min(-150.0 + 3.0 * t, 0.0)


def shock(curve, scenario: str):
    """Curve of the same class with zero rates shocked at the pillars (interpolation unchanged).

    Floor: r' = max(r + Δ, min(r, floor)) — an observed rate already below the floor is kept.
    """
    t = curve.t[1:]
    z = -curve.x / t
    zc = np.array([max(r + shock_bp(scenario, u) * BP, min(r, floor_bp(u) * BP)) for r, u in zip(z, t)])
    return type(curve)(curve.day, curve.pillars, -zc * t)


def irrbb(swaps, day, estr, six, fixing=None) -> dict:
    """ΔEVE (EUR) per scenario: same shock on the zero rates of both curves, full revaluation."""
    v0 = value(swaps, day, estr, six, fixing)
    return {s: value(swaps, day, shock(estr, s), shock(six, s), fixing) - v0 for s in SCENARIOS}


GRID = [0.25, 0.5, 1, 2, 3, 5, 7, 10, 15, 20, 30]


def shocks_yaml(grid=GRID) -> str:
    """IRRBB shocks in the scenario format of project 04 (YAML written by hand, no dependency): zero-rate shock in bp
    per maturity in years, before the floor (the floor depends on the curve level, it is applied at shock time)."""
    lines = ["# IRRBB rate shocks (BCBS 2016, EUR), in bp on zero rates, per maturity (years).",
             "# EBA post-shock floor to apply: max(r + shock, min(r, -150 + 3 t)) bp, capped at 0.",
             "scenarios:"]
    for s in SCENARIOS:
        lines += [f"  irrbb_{s}:", "    type: hypothetical", "    factor: EUR_zero", "    shocks_bp:"]
        lines += [f"      {u}: {shock_bp(s, u):.4f}" for u in grid]
    return "\n".join(lines) + "\n"
