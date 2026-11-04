"""Monotone convex Hagan-West: primitive g, conservation of ∫f, forward continuity, Jacobian, QuantLib benchmark."""
from datetime import date, timedelta

import numpy as np
import pytest

from ratecurves import quotes as c
from ratecurves.curves import CurveHW, estr_curve, euribor6m_curve, primitive_g
from ql_bench import bench_days, estr_curve as estr_ql, euribor6m_curve as e6m_ql, q

DAY = date(2026, 3, 2)
TOL_QL = 1e-10  # same tolerance as log-linear: with ConvexMonotone(0, 1, False), observed gaps ~1e-14
QUOTES = c.read_quotes()

# one (g0, g1) pair per region of the paper: (i) quadratic, (ii), (iii), (iv) same sign, and their mirrors
REGIONS = [(-1.0, 1.0), (1.0, -1.5), (-1.0, 3.0), (1.0, -3.0), (2.0, -0.5), (-2.0, 0.5), (1.0, 2.0), (-1.0, -0.3)]


@pytest.mark.parametrize("g0,g1", REGIONS)
def test_primitive_g(g0, g1):
    assert primitive_g(g0, g1, 0.0) == 0.0
    assert primitive_g(g0, g1, 1.0) == pytest.approx(0.0, abs=1e-15)  # ∫g = 0: conservation of ∫f
    h = 1e-6
    assert (primitive_g(g0, g1, h) / h) == pytest.approx(g0, abs=1e-5)  # g(0) = g0
    assert ((primitive_g(g0, g1, 1.0) - primitive_g(g0, g1, 1 - h)) / h) == pytest.approx(g1, abs=1e-5)  # g(1) = g1


def paper_curve():
    """Data set of the paper (from memory: not checked against the published tables): zero rates at 0.1 / 1 / 4 / 9 /
    20 / 30 years."""
    t = [0.1, 1, 4, 9, 20, 30]
    r = [0.081, 0.07, 0.044, 0.07, 0.04, 0.03]
    pillars = [DAY + timedelta(days=round(x * 365)) for x in t]
    x = [-ri * (p - DAY).days / 365 for ri, p in zip(r, pillars)]
    return CurveHW(DAY, pillars, x)


def forward(k, d, h=1):
    return (k.ln_p(d) - k.ln_p(d + timedelta(days=h))) * 365 / h


def test_conservation_and_continuity_paper():
    k = paper_curve()
    for p, xi in zip(k.pillars, k.x):
        assert k.ln_p(p) == pytest.approx(xi, abs=1e-15)  # ∫f over each interval = discrete forward × length
    for p in k.pillars[:-1]:  # at the last one, intended jump to the extended discrete forward
        left = (k.ln_p(p - timedelta(days=1)) - k.ln_p(p)) * 365
        assert abs(left - forward(k, p)) < 2e-4, p  # forward continuous at the node (gap of order f'·1 day)
    f = [forward(k, DAY + timedelta(days=d)) for d in range(0, 30 * 365, 7)]
    assert min(f) > 0  # no oscillation below zero despite very irregular zeros


def test_flat_curve_exact():
    pillars = [DAY + timedelta(days=d) for d in (90, 400, 2000, 7000)]
    k = CurveHW(DAY, pillars, [-0.03 * (p - DAY).days / 365 for p in pillars])
    for d in range(0, 10000, 37):
        assert forward(k, DAY + timedelta(days=d)) == pytest.approx(0.03, abs=1e-12)


def test_hw_jacobian_equals_finite_differences():
    g = QUOTES[(QUOTES.date == DAY) & (QUOTES.type == "OIS")]
    k = estr_curve(DAY, dict(zip(g.tenor, g.rate)), CurveHW)
    # tiny step: g ~ 1e-6 at the short end, a larger bump changes region (Hagan-West is not differentiable there)
    h = 1e-9
    for j in range(len(k.x)):
        xp, xm = k.x.copy(), k.x.copy()
        xp[j] += h
        xm[j] -= h
        kp, km = CurveHW(DAY, k.pillars, xp), CurveHW(DAY, k.pillars, xm)
        fd = [(i.rate(kp.P) - i.rate(km.P)) / (2 * h) for i in k.instruments]
        assert np.allclose(k.jacobian[:, j], fd, rtol=1e-3, atol=1e-5), j


@pytest.mark.parametrize("day", bench_days(QUOTES)[::3], ids=str)
def test_hw_identical_to_quantlib(day):
    g = QUOTES[QUOTES.date == day]
    o = g[g.type == "OIS"]
    ois = dict(zip(o.tenor, o.rate))
    six = {f"{r.type} {r.tenor}": r.rate for r in g[g.type.isin(["DEPOSIT", "FRA", "IRS"])].itertuples()}
    estr = estr_curve(day, ois, CurveHW)
    kql, _ = estr_ql(day, ois, hw=True)
    c6 = euribor6m_curve(day, six, estr, CurveHW)
    k6, _ = e6m_ql(day, c6.instruments, [v * 100 for v in c6.quotes], kql, hw=True)
    for d in range(0, 40 * 365, 13):
        x = day + timedelta(days=d)
        assert abs(estr.P(x) - kql.discount(q(x))) < TOL_QL, x
        assert abs(c6.P(x) - k6.discount(q(x))) < TOL_QL, x
