"""Pricer, buckets, hedging and IRRBB: NPVs identical to QuantLib, buckets = bumps, hedged portfolio at zero buckets."""
import numpy as np
import QuantLib as ql
import pytest

from ratecurves import dates as dt
from ratecurves import pricing as p
from ratecurves import quotes as c
from ratecurves import risk as r
from ratecurves.curves import Curve, CurveHW
from ratecurves.instruments import IRS
from ql_bench import estr_curve as estr_ql, euribor6m_curve as euribor6m_ql, q

QUOTES = c.read_quotes()
DAY = QUOTES.date.max()
OIS, SIX = c.of_day(QUOTES, DAY)
FIX = p.deposit_fixings(QUOTES)
PF = p.read_portfolio()


@pytest.fixture(scope="module", params=[Curve, CurveHW], ids=["log-linear", "hagan-west"])
def curves(request):
    return request.param, *r.build(DAY, OIS, SIX, request.param)


def test_par_swap_is_worth_zero(curves):
    _, estr, six = curves
    spot = dt.add_business_days(DAY, 2)
    for tenor in ["2Y", "7Y", "10Y", "30Y"]:
        s = p.Swap(spot, tenor, IRS(spot, tenor).rate(six.P, estr.P), 1e8)
        assert abs(s.value(DAY, six.P, estr.P)) < 1e-10 * s.N


def test_portfolio_npvs_identical_to_quantlib(curves):
    cls, estr, six = curves
    kestr, _ = estr_ql(DAY, OIS, hw=cls is CurveHW)
    k6, _ = euribor6m_ql(DAY, six.instruments, [x * 100 for x in six.quotes], kestr, hw=cls is CurveHW)
    idx = ql.Euribor6M(ql.YieldTermStructureHandle(k6))
    engine = ql.DiscountingSwapEngine(ql.YieldTermStructureHandle(kestr))
    try:
        for s in PF:
            for f in s.fixings(DAY):
                idx.addFixing(q(f), FIX(f), True)
            sw = ql.MakeVanillaSwap(ql.Period(s.tenor), idx, s.K, ql.Period(0, ql.Days), effectiveDate=q(s.start),
                                    nominal=s.N, swapType=ql.Swap.Payer if s.payer else ql.Swap.Receiver,
                                    fixedLegTenor=ql.Period(1, ql.Years),
                                    fixedLegDayCount=ql.Thirty360(ql.Thirty360.BondBasis),
                                    fixedLegConvention=ql.ModifiedFollowing,
                                    fixedLegTerminationDateConvention=ql.ModifiedFollowing,
                                    fixedLegEndOfMonth=True, floatingLegEndOfMonth=True, pricingEngine=engine)
            assert abs(sw.NPV() - s.value(DAY, six.P, estr.P, FIX)) < 1e-10 * s.N, s.name
    finally:
        ql.IndexManager.instance().clearHistories()


def _bumped_value(cls, key, h):
    """Portfolio value after a shock h (in %) on the quote `key` (label from `risk.labels`)."""
    ois, six = dict(OIS), dict(SIX)
    if key.startswith("OIS "):
        ois[key[4:]] += h
    else:
        six[key] += h
    return r.value(PF, DAY, *r.build(DAY, ois, six, cls), FIX)


def test_buckets_equal_bumps(curves):
    """Central bump of 0.01 bp. Hagan-West is not differentiable at region boundaries: relative gap ~1e-5."""
    cls, estr, six = curves
    v, b = r.buckets(PF, DAY, estr, six, FIX)
    assert abs(v - r.value(PF, DAY, estr, six, FIX)) < 1e-6
    tol = 1e-7 if cls is Curve else 1e-4
    lab = r.labels(estr, six)
    for key in ["OIS 1Y", "OIS 10Y", "OIS 30Y", "DEPOSIT 6M", "FRA 6x12", "IRS 5Y", "IRS 10Y", "IRS 30Y"]:
        h = 1e-4
        bump = (_bumped_value(cls, key, h) - _bumped_value(cls, key, -h)) / (2 * h) / 100
        assert abs(b[lab.index(key)] - bump) < tol * np.abs(b).max(), key


def test_sum_of_buckets_equals_parallel_dv01(curves):
    cls, estr, six = curves
    _, b = r.buckets(PF, DAY, estr, six, FIX)
    up = r.value(PF, DAY, *r.build(DAY, {k: x + .01 for k, x in OIS.items()},
                                   {k: x + .01 for k, x in SIX.items()}, cls), FIX)
    dn = r.value(PF, DAY, *r.build(DAY, {k: x - .01 for k, x in OIS.items()},
                                   {k: x - .01 for k, x in SIX.items()}, cls), FIX)
    assert abs(b.sum() - (up - dn) / 2) < 1e-3 * abs(b.sum())


def test_zero_dv01_equals_bump(curves):
    _, estr, six = curves
    def shifted(k, h):
        return type(k)(k.day, k.pillars, k.x - h * k.t[1:])
    up = r.value(PF, DAY, shifted(estr, 1e-6), shifted(six, 1e-6), FIX)
    dn = r.value(PF, DAY, shifted(estr, -1e-6), shifted(six, -1e-6), FIX)
    assert abs(r.dv01_zero(PF, DAY, estr, six, FIX) - (up - dn) / 2e-6 * 1e-4) < 1e-6 * abs((up - dn) / 2e-2)


def test_hedged_portfolio_at_zero_buckets(curves):
    _, estr, six = curves
    _, b = r.buckets(PF, DAY, estr, six, FIX)
    h, B = r.hedge(DAY, estr, six, b)
    assert np.abs(B - np.diag(np.diag(B))).max() < 1e-12 * np.abs(B).max()  # at par, each instrument sees its own quote
    assert np.abs(b + B @ h).max() < 1e-9 * np.abs(b).max()
    # independent check: the hedge notionals of a 10Y payer swap concentrate on the 10Y IRS
    spot = dt.add_business_days(DAY, 2)
    s = p.Swap(spot, "10Y", 0.03, 1e7)
    h10, _ = r.hedge(DAY, estr, six, r.buckets([s], DAY, estr, six)[1])
    assert abs(h10[r.labels(estr, six).index("IRS 10Y")] + 1e7) < 1e-6 * 1e7


def test_irrbb_shocks():
    assert r.shock_bp("short_up", 0) == 250 and abs(r.shock_bp("steepener", 0) + 162.5) < 1e-12
    assert abs(r.shock_bp("steepener", 1e3) - 90) < 1e-9 and abs(r.shock_bp("flattener", 1e3) + 60) < 1e-9
    assert r.floor_bp(0) == -150 and r.floor_bp(10) == -120 and r.floor_bp(60) == 0


def test_parallel_shock_and_floor():
    pillars = [DAY.replace(year=DAY.year + n) for n in (1, 5, 30)]
    t = Curve(DAY, pillars, [0, 0, 0]).t[1:]
    k = Curve(DAY, pillars, -0.01 * t)  # zeros at 1%
    z = lambda c: -c.x / c.t[1:]
    assert np.allclose(z(r.shock(k, "parallel_up")), 0.03, rtol=0, atol=1e-15)
    # −200 bp on 1%: −1%, above the floor at 1 and 5 years (−147 and −135 bp); at 30 years floor ≈ −60 bp
    expected = [-0.01, -0.01, r.floor_bp(t[2]) * 1e-4]
    assert np.allclose(z(r.shock(k, "parallel_down")), expected, rtol=0, atol=1e-15)
    low = Curve(DAY, pillars, 0.02 * t)  # zeros at −2%, already below the floor: kept
    assert np.allclose(z(r.shock(low, "parallel_down")), -0.02, rtol=0, atol=1e-15)


def test_shock_export_project_04():
    yaml = pytest.importorskip("yaml")
    s = yaml.safe_load(r.shocks_yaml())["scenarios"]
    assert len(s) == 6 and s["irrbb_parallel_down"]["shocks_bp"][10] == -200
    assert s["irrbb_short_up"]["shocks_bp"][2] == pytest.approx(r.shock_bp("short_up", 2), abs=1e-4)
