"""Calibration instruments: dates precomputed once, implied rate computed from a function P(date).

P can return floats or `Dual` numbers (ratecurves/curves.py): the same code then gives the rate and its gradient.
"""
from datetime import date, timedelta

from ratecurves import dates as dt


def maturity(spot: date, tenor: str) -> date:
    """UNADJUSTED swap maturity (spot + tenor), starting point of the backward schedule (ql.MakeOIS).

    End-of-month rule: spot = last business day of the month → maturity at the last day of the month.
    """
    n, u = dt.parse_tenor(tenor)
    if u == "W":
        return spot + timedelta(weeks=n)
    end = dt.add_months(spot, n * 12 if u == "Y" else n)
    return dt.last_day_of_month(end) if dt.is_end_of_month(spot) else end


class OIS:
    """€STR OIS: spot → spot + tenor, a single payment up to 1 year then annual, ACT/360, MF end of month, paid T+1.

    Floating leg of one period = P(a)/P(b) - 1 (telescoped €STR compounding), paid one business day later.
    """

    def __init__(self, spot: date, tenor: str):
        self.tenor = tenor
        n, u = dt.parse_tenor(tenor)
        if u == "D":
            raise ValueError("OIS: tenor in weeks, months or years")
        # up to 1 year, the annual backward generation gives a single period
        sched = dt.schedule(spot, maturity(spot, tenor), "1Y", "MF", eom=True)
        self.periods = [(a, b, dt.add_business_days(b, 1), dt.year_fraction(a, b, "ACT/360"))
                        for a, b in zip(sched, sched[1:])]
        self.pillar = self.periods[-1][2]  # last relevant date: last payment

    def rate(self, P):
        floating = fixed = 0.0
        for a, b, payment, tau in self.periods:
            p = P(payment)
            floating += (P(a) / P(b) - 1) * p
            fixed += tau * p
        return floating / fixed

    def annuity(self, Pd):
        return sum(tau * Pd(payment) for _, _, payment, tau in self.periods)


class Deposit:
    """EURIBOR 6M deposit / FRA: spot + m months → + 6M, ACT/360, MF end of month. Rate = simple forward of the 6M curve."""

    def __init__(self, spot: date, start_month: int = 0):
        self.tenor = f"{start_month}x{start_month + 6}" if start_month else "6M"
        self.start = dt.advance(spot, f"{start_month}M", "MF", eom=True) if start_month else spot
        self.end = dt.advance(self.start, "6M", "MF", eom=True)
        self.tau = dt.year_fraction(self.start, self.end, "ACT/360")
        self.pillar = self.end

    def rate(self, P6, Pd=None):
        return (P6(self.start) / P6(self.end) - 1) / self.tau

    def annuity(self, Pd):
        return self.tau * Pd(self.end)


class IRS:
    """Swap against EURIBOR 6M: annual fixed 30/360, semi-annual floating ACT/360, MF end of month, backward.

    "Par" floating coupon (QuantLib default setting): 6M forward over the accrual period, paid at the end of the
    period and discounted on the Pd curve (€STR, cash EUR CSA).
    """

    def __init__(self, spot: date, tenor: str):
        self.tenor = tenor
        end = maturity(spot, tenor)
        f = dt.schedule(spot, end, "1Y", "MF", eom=True)
        v = dt.schedule(spot, end, "6M", "MF", eom=True)
        self.fixed = [(b, dt.year_fraction(a, b, "30/360")) for a, b in zip(f, f[1:])]
        self.floating = [(a, b, dt.year_fraction(a, b, "ACT/360")) for a, b in zip(v, v[1:])]
        self.pillar = v[-1]

    def rate(self, P6, Pd=None):
        Pd = Pd or P6
        floating = sum((P6(a) / P6(b) - 1) * Pd(b) for a, b, _ in self.floating)
        return floating / self.annuity(Pd)

    def annuity(self, Pd):
        return sum(tau * Pd(b) for b, tau in self.fixed)
