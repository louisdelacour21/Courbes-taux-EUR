"""QuantLib benchmark of the €STR curve: same quotes, same conventions, gaps < 1e-10 required.

QuantLib: OISRateHelper (ql.Estr, spot 2, payment T+1 MF TARGET, end of month, LastRelevantDate pillar),
PiecewiseLogLinearDiscount in ACT/365F, bootstrap accuracy 1e-14.
"""
import random
from datetime import timedelta

import QuantLib as ql
import pytest

from ratecurves import dates as dt
from ratecurves import quotes as c
from ratecurves.curves import estr_curve
from ratecurves.instruments import OIS
from ql_bench import bench_days, estr_curve as curve_ql, q

TOL = 1e-10
RNG = random.Random(20261104)
QUOTES = c.read_quotes()


@pytest.mark.parametrize("day", bench_days(QUOTES), ids=str)
def test_estr_curve_identical_to_quantlib(day):
    g = QUOTES[(QUOTES.date == day) & (QUOTES.type == "OIS")]
    quotes = dict(zip(g.tenor, g.rate))
    ours = estr_curve(day, quotes)
    kql, helpers = curve_ql(day, quotes)

    # pillars
    assert [h.pillarDate() for h in helpers] == [q(d) for d in ours.pillars]
    # discount factors on 500 dates, up to 40 years (beyond the last pillar: extrapolation)
    for _ in range(500):
        d = day + timedelta(days=RNG.randint(0, 40 * 365))
        assert abs(ours.P(d) - kql.discount(q(d))) < TOL, d
    # par rates of the calibration instruments, valued by QuantLib on its curve
    for h, i in zip(helpers, ours.instruments):
        assert abs(h.impliedQuote() - i.rate(ours.P)) < TOL, i.tenor
    # 200 random OIS: start shifted up to 5 years, tenor from 1 week to 30 years
    projection = ql.YieldTermStructureHandle(kql)
    spot = dt.add_business_days(day, 2)
    for _ in range(200):
        start = dt.add_business_days(spot, RNG.randint(0, 5 * 252))
        tenor = RNG.choice(["1W", "3W", "1M", "5M", "11M", "1Y", "13M", "18M", "2Y", "7Y", "10Y", "17Y", "30Y"])
        sw = ql.MakeOIS(ql.Period(tenor), ql.Estr(projection), 0.0, effectiveDate=q(start), paymentLag=1,
                        paymentAdjustmentConvention=ql.ModifiedFollowing, paymentCalendar=ql.TARGET(),
                        endOfMonth=True, discountingTermStructure=projection)
        assert abs(sw.fairRate() - OIS(start, tenor).rate(ours.P)) < TOL, (start, tenor)
