"""PnL explain: identity of the decomposition, zero residual under pure carry, third order on a parallel shock."""
from datetime import timedelta, date

import pytest

from ratecurves import dates as dt
from ratecurves import pnl
from ratecurves import pricing as p
from ratecurves import quotes as c
from ratecurves import risk as r
from ratecurves.curves import Curve, CurveHW

QUOTES = c.read_quotes()
DAYS = sorted(QUOTES.date.unique())
D0, D1 = DAYS[-2], DAYS[-1]
PF, FIX = p.read_portfolio(), p.deposit_fixings(QUOTES)


def carried(cls):
    q0 = c.of_day(QUOTES, D0)
    return q0, pnl.carried_quotes(*r.build(D0, *q0, cls), *q0, D1)


@pytest.mark.parametrize("cls", [Curve, CurveHW])
def test_pure_carry_zero_residual(cls):
    q0, qc = carried(cls)
    e = pnl.explain(PF, D0, D1, q0, qc, FIX, cls)
    assert abs(e["delta"]) < 1e-6 and abs(e["gamma"]) < 1e-6 and abs(e["residual"]) < 1e-6
    assert e["total"] == pytest.approx(e["carry"] + e["fixings"], abs=1e-6)


@pytest.mark.parametrize("cls", [Curve, CurveHW])
def test_parallel_shock_third_order_residual(cls):
    q0, qc = carried(cls)
    res = []
    for d in (5, 10):
        q1 = tuple({k: v + d / 100 for k, v in q.items()} for q in qc)
        e = pnl.explain(PF, D0, D1, q0, q1, FIX, cls)
        assert abs(e["residual"]) < 1e-3 * abs(e["delta"])
        res.append(e["residual"])
    assert res[1] / res[0] == pytest.approx(8, rel=0.05)  # doubling the shock multiplies the residual by 2³


def test_paid_cashflows():
    s = p.Swap(date(2025, 6, 2), "2Y", 0.03, 1e6)  # first fixed coupon paid with the 2nd floating one, in June 2026
    (bf, tf), (a, bv, tv) = s.sched.fixed[0], s.sched.floating[1]
    assert bf == bv and DAYS[0] < bf <= D1
    expected = 1e6 * (tv * FIX(dt.add_business_days(a, -2)) - 0.03 * tf)
    assert s.cashflows(bf - timedelta(days=1), bf, FIX) == pytest.approx(expected, rel=1e-14)
    assert s.cashflows(bf, D1, FIX) == 0
