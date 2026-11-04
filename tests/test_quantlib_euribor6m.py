"""QuantLib benchmark of the EURIBOR 6M curve: same quotes, same €STR discount curve, gaps < 1e-10.

QuantLib: DepositRateHelper / FraRateHelper on ql.Euribor6M, SwapRateHelper (fixed annual MF 30/360 Bond Basis,
end of month, exogenous €STR discounting), PiecewiseLogLinearDiscount in ACT/365F, accuracy 1e-14.
"""
import random
from datetime import timedelta

import QuantLib as ql
import pytest

from ratecurves import dates as dt
from ratecurves import quotes as c
from ratecurves.curves import estr_curve, euribor6m_curve, instrument_6m
from ratecurves.instruments import IRS
from ql_bench import bench_days, estr_curve as estr_ql, euribor6m_curve as euribor6m_ql, q

TOL = 1e-10
RNG = random.Random(20261105)
QUOTES = c.read_quotes()


@pytest.mark.parametrize("day", bench_days(QUOTES), ids=str)
def test_euribor6m_curve_identical_to_quantlib(day):
    ois, six = c.of_day(QUOTES, day)
    estr = estr_curve(day, ois)
    ours = euribor6m_curve(day, six, estr)
    kestr, _ = estr_ql(day, ois)
    k6, helpers = euribor6m_ql(day, ours.instruments, [r * 100 for r in ours.quotes], kestr)

    assert [h.pillarDate() for h in helpers] == [q(d) for d in ours.pillars]
    for _ in range(500):
        d = day + timedelta(days=RNG.randint(0, 40 * 365))
        assert abs(ours.P(d) - k6.discount(q(d))) < TOL, d
    for h, i in zip(helpers, ours.instruments):
        assert abs(h.impliedQuote() - i.rate(ours.P, estr.P)) < TOL, i.tenor

    # 200 random swaps against EURIBOR 6M: start shifted up to 5 years, tenor from 1 to 30 years
    projection, disc = ql.YieldTermStructureHandle(k6), ql.YieldTermStructureHandle(kestr)
    spot = dt.add_business_days(day, 2)
    for _ in range(200):
        start = dt.add_business_days(spot, RNG.randint(0, 5 * 252))
        tenor = RNG.choice(["1Y", "18M", "2Y", "3Y", "5Y", "7Y", "10Y", "13Y", "17Y", "20Y", "30Y"])
        sw = ql.MakeVanillaSwap(ql.Period(tenor), ql.Euribor6M(projection), 0.0, ql.Period(0, ql.Days),
                                effectiveDate=q(start), fixedLegTenor=ql.Period(1, ql.Years),
                                fixedLegDayCount=ql.Thirty360(ql.Thirty360.BondBasis),
                                fixedLegConvention=ql.ModifiedFollowing,
                                fixedLegTerminationDateConvention=ql.ModifiedFollowing,
                                fixedLegEndOfMonth=True, floatingLegEndOfMonth=True,
                                discountingTermStructure=disc)
        assert abs(sw.fairRate() - IRS(start, tenor).rate(ours.P, estr.P)) < TOL, (start, tenor)


def test_irs_2y_dropped_when_its_pillar_differs_by_one_day():
    """On 33 days, the end of the 18x24 FRA and of the 2Y IRS differ by one day: keeping both makes J nearly singular."""
    pillar = lambda d, k: instrument_6m(dt.add_business_days(d, 2), k).pillar  # noqa: E731
    day = next(d for d in sorted(QUOTES.date.unique()) if pillar(d, "FRA 18x24") != pillar(d, "IRS 2Y"))
    ois, six_q = c.of_day(QUOTES, day)
    estr = estr_curve(day, ois)
    six = euribor6m_curve(day, six_q, estr)
    assert not any(isinstance(i, IRS) and i.tenor == "2Y" for i in six.instruments)
    assert min((b - a).days for a, b in zip(six.pillars, six.pillars[1:])) > 5
