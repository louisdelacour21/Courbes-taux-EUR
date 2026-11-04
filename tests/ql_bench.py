"""Builds the QuantLib reference curves shared by the benchmarks (QuantLib is used in tests only)."""
from datetime import date

import QuantLib as ql

from ratecurves import dates as dt


def q(d: date) -> ql.Date:
    return ql.Date(d.day, d.month, d.year)


def bench_days(quotes):
    days = sorted(quotes.date.unique())
    # one day in 10, plus every day whose spot is a last business day of the month (end-of-month rule)
    month_ends = [d for d in days if dt.is_end_of_month(dt.add_business_days(d, 2))]
    return sorted(set(days[::10]) | set(month_ends) | {days[-1]})


def curve(day: date, helpers, hw=False):
    """hw: monotone convex Hagan-West, no quadratic blending (0), monotone (1), no positivity floor."""
    if hw:
        k = ql.PiecewiseConvexMonotoneForward(q(day), helpers, ql.Actual365Fixed(), ql.IterativeBootstrap(1e-14),
                                              ql.ConvexMonotone(0.0, 1.0, False))
    else:
        k = ql.PiecewiseLogLinearDiscount(q(day), helpers, ql.Actual365Fixed(), [], [], ql.LogLinear(),
                                          ql.IterativeBootstrap(1e-14))
    k.enableExtrapolation()
    return k


def estr_curve(day: date, ois_quotes: dict, hw=False):
    """OISRateHelper: ql.Estr, spot 2, payment T+1 MF TARGET, end of month, LastRelevantDate pillar."""
    ql.Settings.instance().evaluationDate = q(day)
    helpers = [ql.OISRateHelper(2, ql.Period(t), ql.QuoteHandle(ql.SimpleQuote(v / 100)), ql.Estr(),
                                paymentLag=1, paymentConvention=ql.ModifiedFollowing, paymentCalendar=ql.TARGET(),
                                endOfMonth=True, pillar=ql.Pillar.LastRelevantDate)
               for t, v in ois_quotes.items()]
    return curve(day, helpers, hw), helpers


def euribor6m_curve(day: date, instruments, quotes: list, estr, hw=False):
    """Same instruments as ours (list already sorted and deduplicated), discounting on the €STR curve `estr`."""
    ql.Settings.instance().evaluationDate = q(day)
    disc = ql.YieldTermStructureHandle(estr)
    helpers = []
    for i, v in zip(instruments, quotes):
        h = ql.QuoteHandle(ql.SimpleQuote(v / 100))
        if i.tenor == "6M":
            helpers.append(ql.DepositRateHelper(h, ql.Euribor6M()))
        elif "x" in i.tenor:
            helpers.append(ql.FraRateHelper(h, int(i.tenor.split("x")[0]), ql.Euribor6M()))
        else:
            helpers.append(ql.SwapRateHelper(h, ql.Period(i.tenor), ql.TARGET(), ql.Annual, ql.ModifiedFollowing,
                                             ql.Thirty360(ql.Thirty360.BondBasis), ql.Euribor6M(),
                                             ql.QuoteHandle(), ql.Period(0, ql.Days), disc, 2,
                                             ql.Pillar.LastRelevantDate, ql.Date(), True))
    return curve(day, helpers, hw), helpers
