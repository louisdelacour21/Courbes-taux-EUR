"""EUR swap pricer against EURIBOR 6M (conventions of the calibration IRS): new, forward-starting or seasoned.

V = s N [Σ τ_j F_j Pd(t_j) − K Σ τ_i Pd(t_i)], s = +1 fixed-rate payer. Cash flows paid on or before the valuation day
are excluded (as in QuantLib); a floating coupon whose fixing (T-2) is before the valuation day takes the published
fixing, otherwise the forward of the 6M curve. P6 and Pd can return `Dual` numbers.
"""
from datetime import date
from pathlib import Path

import pandas as pd

from ratecurves import dates as dt
from ratecurves.instruments import IRS

PORTFOLIO = Path(__file__).resolve().parent.parent / "data" / "portfolio.csv"


class Swap:
    def __init__(self, start: date, tenor: str, fixed_rate: float, notional: float, payer: bool = True, name: str = ""):
        self.sched = IRS(start, tenor)  # same schedule as the calibration IRS, from the start date
        self.start, self.tenor, self.K, self.N, self.payer, self.name = start, tenor, fixed_rate, notional, payer, name

    def fixings(self, day: date) -> list[date]:
        """Past fixing dates of the floating coupons still alive."""
        return [f for a, b, _ in self.sched.floating if b > day and (f := dt.add_business_days(a, -2)) < day]

    def value(self, day: date, P6, Pd, fixing=None, cutoff: date | None = None):
        """`fixing(date)`: published EURIBOR 6M fixing (decimal), required for seasoned swaps.

        `cutoff`: published fixings for dates before `cutoff` (default: day), forwards beyond.
        """
        cutoff = cutoff or day
        fixed = sum(tau * Pd(b) for b, tau in self.sched.fixed if b > day)
        floating = 0.0
        for a, b, tau in self.sched.floating:
            if b <= day:
                continue
            f = dt.add_business_days(a, -2)
            floating = floating + tau * (fixing(f) if f < cutoff else (P6(a) / P6(b) - 1) / tau) * Pd(b)
        return (1 if self.payer else -1) * self.N * (floating - self.K * fixed)

    def cashflows(self, day0: date, day1: date, fixing) -> float:
        """Net cash flows paid in ]day0, day1] (all fixings published)."""
        fixed = sum(tau for b, tau in self.sched.fixed if day0 < b <= day1)
        floating = sum(tau * fixing(dt.add_business_days(a, -2)) for a, b, tau in self.sched.floating if day0 < b <= day1)
        return (1 if self.payer else -1) * self.N * (floating - self.K * fixed)


def deposit_fixings(quotes: pd.DataFrame):
    """Assumption: EURIBOR 6M fixing of the day = reconstructed 6M deposit quote of that day (fixings are licensed
    by EMMI). Assumed component, presented as such.

    Fixings before the data (three, mid-2025, seasoned swaps): first available quote.
    """
    d = quotes[quotes.type == "DEPOSIT"].set_index("date").rate / 100
    return lambda day: float(d[day] if day >= d.index[0] else d.iloc[0])


def read_portfolio(path=PORTFOLIO) -> list[Swap]:
    df = pd.read_csv(path, parse_dates=["start"])
    return [Swap(r.start.date(), r.tenor, r.fixed_rate / 100, r.notional, r.side == "payer", r.name)
            for r in df.itertuples()]
