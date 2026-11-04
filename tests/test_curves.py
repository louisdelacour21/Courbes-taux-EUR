"""€STR curve: log-linear interpolation, repricing at par to 1e-13, analytic Jacobian."""
from datetime import date

import numpy as np
import pytest

from ratecurves import dates as dt
from ratecurves import quotes as c
from ratecurves.curves import Curve, Dual, estr_curve

DAY = date(2026, 3, 2)


@pytest.fixture(scope="module")
def quotes():
    return c.read_quotes()


def ois_of_day(quotes, day):
    g = quotes[(quotes.date == day) & (quotes.type == "OIS")]
    return dict(zip(g.tenor, g.rate))


def test_log_linear_interpolation():
    pillars = [date(2027, 3, 2), date(2028, 3, 2)]
    k = Curve(DAY, pillars, [-0.02, -0.05])
    assert k.P(DAY) == 1.0
    assert k.ln_p(pillars[1]) == pytest.approx(-0.05, abs=1e-15)
    t = lambda d: dt.year_fraction(DAY, d, "ACT/365F")
    m = date(2027, 9, 1)
    w = (t(m) - t(pillars[0])) / (t(pillars[1]) - t(pillars[0]))
    assert k.ln_p(m) == pytest.approx(-0.02 + w * (-0.03), abs=1e-15)
    # beyond the last pillar: flat forward (extension of the last segment)
    far = date(2030, 3, 1)
    slope = -0.03 / (t(pillars[1]) - t(pillars[0]))
    assert k.ln_p(far) == pytest.approx(-0.05 + slope * (t(far) - t(pillars[1])), abs=1e-15)
    with pytest.raises(ValueError):
        k.P(date(2026, 1, 1))


def test_dual_arithmetic():
    a, b = Dual(3.0, np.array([1.0, 0.0])), Dual(2.0, np.array([0.0, 1.0]))
    r = (a / b - 1) * a + 2.0 * b - 1 / a
    va, vb = 3.0, 2.0  # r = a²/b - a + 2b - 1/a
    assert r.v == pytest.approx(va**2 / vb - va + 2 * vb - 1 / va)
    np.testing.assert_allclose(r.g, [2 * va / vb - 1 + 1 / va**2, -va**2 / vb**2 + 2])


def test_repricing_at_par_every_10_days(quotes):
    days = sorted(quotes.date.unique())
    for day in days[::10] + [days[-1]]:
        q = ois_of_day(quotes, day)
        k = estr_curve(day, q)
        gaps = [abs(i.rate(k.P) - q[i.tenor] / 100) for i in k.instruments]
        assert max(gaps) < 1e-13, day


def test_jacobian_equals_finite_differences(quotes):
    k = estr_curve(DAY, ois_of_day(quotes, DAY))
    h = 1e-7
    for j in range(len(k.x)):
        dx = np.zeros(len(k.x))
        dx[j] = h
        up, down = Curve(DAY, k.pillars, k.x + dx), Curve(DAY, k.pillars, k.x - dx)
        fd = [(i.rate(up.P) - i.rate(down.P)) / (2 * h) for i in k.instruments]
        np.testing.assert_allclose(k.jacobian[:, j], fd, rtol=1e-6, atol=1e-9)


def test_curve_close_to_the_generating_curve():
    """On noiseless quotes, the bootstrapped DFs at the pillars fall back on the curve that generated them."""
    m = c._market()
    r = m.loc[DAY]
    true = c.discount_factors(DAY, r.iloc[:6].tolist(), r.estr)
    spot = dt.add_business_days(DAY, 2)
    q = {t: c.ois_par(true, spot, t) * 100 for t in c.OIS_TENORS}
    k = estr_curve(DAY, q)
    # intermediate cash flow dates (spot, annual coupons) are interpolated, hence a gap at the pillars:
    # ~1e-6 up to 10 years, up to ~4e-4 at 30 years where pillars are 5 years apart
    gaps = [abs(k.P(d) / true(d) - 1) for d in k.pillars]
    assert max(gaps[:18]) < 1e-5 and max(gaps) < 5e-4
    # between pillars, the step forward of log-linear departs from the smooth curve (up to ~2e-3 on the
    # 25-30 year segment): this is what step 6 (Hagan-West, leave-one-out) must measure and reduce
    between = [DAY + (k.pillars[-1] - DAY) * f for f in np.linspace(0.01, 1, 200)]
    assert max(abs(k.P(d) / true(d) - 1) for d in between) < 3e-3
