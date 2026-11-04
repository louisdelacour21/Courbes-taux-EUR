"""Reconstruction of daily EUR quotes from ECB series, and reading of a quote file.

There is no free source of swap quotes: the levels are reconstructed (assumptions.md).
File format (one row per quote, rates in %): date,type,tenor,rate,source
  type   : ESTR (tenor ON), OIS, DEPOSIT, FRA (tenor "1x7"), IRS (against EURIBOR 6M)
  source : "reconstructed" or "real" — real quotes load with the same format.

`python -m ratecurves.quotes` regenerates data/quotes.csv and prints the figures quoted in assumptions.md.
"""
import math
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from ratecurves import dates as dt
from ratecurves.ecb import END, START, series
from ratecurves.instruments import IRS, OIS, Deposit

FILE = Path(__file__).resolve().parent.parent / "data" / "quotes.csv"
COLUMNS = ["date", "type", "tenor", "rate", "source"]
SOURCES = {"reconstructed", "real"}

OIS_TENORS = ["1W", "2W", "1M", "2M", "3M", "6M", "9M", "1Y", "18M", "2Y", "3Y", "4Y", "5Y", "6Y", "7Y",
              "8Y", "9Y", "10Y", "12Y", "15Y", "20Y", "25Y", "30Y"]
FRA_STARTS = [1, 2, 3, 6, 9, 12, 18]  # FRA 1x7 ... 18x24
IRS_TENORS = ["2Y", "3Y", "4Y", "5Y", "6Y", "7Y", "8Y", "9Y", "10Y", "12Y", "15Y", "20Y", "25Y", "30Y"]
NOISE_BP = {"OIS": 0.2, "IRS": 0.3, "FRA": 0.4, "DEPOSIT": 0.5}  # standard deviation of the Gaussian noise
TAU_SHIFT = 1.0  # years: speed at which the €STR - AAA gap dies out along the curve
JUMP = {"type": "IRS", "tenor": "10Y", "start": date(2026, 5, 4), "days": 5, "bp": 2.5}
SEED = 20261101


def svensson(t: float, b0, b1, b2, b3, t1, t2) -> float:
    """ECB zero rate (Svensson, continuous compounding, %) at t years."""
    if t < 1e-8:
        return b0 + b1
    x1, x2 = t / t1, t / t2
    f1 = (1 - math.exp(-x1)) / x1
    return b0 + b1 * f1 + b2 * (f1 - math.exp(-x1)) + b3 * ((1 - math.exp(-x2)) / x2 - math.exp(-x2))


def shift(t: float, params, estr: float) -> float:
    """Spread (%) added to the AAA zero rate: €STR - instantaneous AAA zero, dying out exponentially."""
    r0 = math.log1p(estr / 36000) * 36500  # €STR (ACT/360, 1 day) in continuous compounding
    return (r0 - (params[0] + params[1])) * math.exp(-t / TAU_SHIFT)


def discount_factors(day: date, params, estr: float):
    """Reconstructed €STR discount factors for the quote date `day`."""
    def P(d: date) -> float:
        t = dt.year_fraction(day, d, "ACT/365F")
        return math.exp(-(svensson(t, *params) + shift(t, params, estr)) / 100 * t)
    return P


def forward(P, a: date, b: date) -> float:
    """Simple ACT/360 rate between a and b (decimal)."""
    return (P(a) / P(b) - 1) / dt.year_fraction(a, b, "ACT/360")


def ois_par(P, spot: date, tenor: str) -> float:
    return OIS(spot, tenor).rate(P)


def irs_par(P, spot: date, tenor: str, basis: float) -> float:
    """Swap rate against EURIBOR 6M (instruments.IRS conventions), 6M forward = €STR forward + basis."""
    i = IRS(spot, tenor)
    num = sum((forward(P, a, b) + basis) * tau * P(b) for a, b, tau in i.floating)
    return num / sum(tau * P(b) for b, tau in i.fixed)


def _market() -> pd.DataFrame:
    """Svensson parameters and €STR on the days common to both series."""
    names = ["beta0", "beta1", "beta2", "beta3", "tau1", "tau2", "estr"]
    return pd.DataFrame({n: series(n) for n in names}).dropna()


def monthly_bases(market: pd.DataFrame) -> dict:
    """EURIBOR 6M - OIS basis per month: ECB monthly average minus the average reconstructed 6M OIS forward."""
    euribor = series("euribor6m")
    model: dict[str, list] = {}
    for day, r in market.iterrows():
        P = discount_factors(day, r.iloc[:6].tolist(), r.estr)
        spot = dt.add_business_days(day, 2)
        d = Deposit(spot)
        model.setdefault(f"{day:%Y-%m}", []).append(forward(P, d.start, d.end))
    bases, last = {}, None
    for month, f in model.items():
        if month in euribor.index:
            last = euribor[month] / 100 - float(np.mean(f))
        bases[month] = last  # month not yet published: basis of the last known month
    return bases


def reconstruct(start: date = START, end: date = END, seed: int = SEED, noise: bool = True) -> pd.DataFrame:
    market = _market()
    bases = monthly_bases(market)
    rng = np.random.default_rng(seed)
    jump_days = [j for j in market.index if j >= JUMP["start"]][: JUMP["days"]]
    rows = []
    for day, r in market.loc[start:end].iterrows():
        P = discount_factors(day, r.iloc[:6].tolist(), r.estr)
        spot = dt.add_business_days(day, 2)
        basis = bases[f"{day:%Y-%m}"]
        quotes = [("OIS", t, ois_par(P, spot, t)) for t in OIS_TENORS]
        for d in [Deposit(spot)] + [Deposit(spot, m) for m in FRA_STARTS]:
            quotes.append(("DEPOSIT" if d.tenor == "6M" else "FRA", d.tenor, forward(P, d.start, d.end) + basis))
        quotes += [("IRS", t, irs_par(P, spot, t, basis)) for t in IRS_TENORS]

        rows.append((day, "ESTR", "ON", r.estr))  # published fixing, no noise
        for typ, tenor, rate in quotes:
            rate *= 100
            if noise:
                rate += rng.normal(0, NOISE_BP[typ]) / 100
                if (typ, tenor) == (JUMP["type"], JUMP["tenor"]) and day in jump_days:
                    rate += JUMP["bp"] / 100
            rows.append((day, typ, tenor, rate))
    df = pd.DataFrame(rows, columns=COLUMNS[:4])
    df["rate"] = df.rate.round(5)
    df["source"] = "reconstructed"
    return df


def _valid_tenor(typ: str, tenor: str) -> bool:
    if typ == "ESTR":
        return tenor == "ON"
    try:
        if typ == "FRA":
            a, b = (int(x) for x in tenor.split("x"))
            return 0 <= a < b
        return dt.parse_tenor(tenor)[0] > 0
    except ValueError:
        return False


def read_quotes(path=FILE) -> pd.DataFrame:
    """Loads and validates a quote file (reconstructed or real)."""
    df = pd.read_csv(path, dtype={"tenor": str, "type": str, "source": str})
    if list(df.columns) != COLUMNS:
        raise ValueError(f"expected columns {COLUMNS}, found {list(df.columns)}")
    df["date"] = pd.to_datetime(df.date, format="%Y-%m-%d").dt.date
    df["rate"] = pd.to_numeric(df.rate, errors="raise")
    errors = []
    if not df.rate.map(math.isfinite).all():
        errors.append("non-finite rates")
    if bad := set(df.source) - SOURCES:
        errors.append(f"unknown sources {bad}")
    if bad := {(t, n) for t, n in zip(df.type, df.tenor) if t not in NOISE_BP and t != "ESTR" or not _valid_tenor(t, n)}:
        errors.append(f"invalid type/tenor {sorted(bad)[:5]}")
    if df.duplicated(["date", "type", "tenor"]).any():
        errors.append("duplicate quotes")
    if errors:
        raise ValueError("; ".join(errors))
    return df


if __name__ == "__main__":
    df = reconstruct()
    FILE.parent.mkdir(exist_ok=True)
    df.to_csv(FILE, index=False, date_format="%Y-%m-%d")
    print(f"{len(df)} quotes, {df.date.nunique()} days, {df.date.min()} -> {df.date.max()}")

    market = _market().loc[START:END]
    for t in (0.25, 1, 2, 5, 10):
        d = [shift(t, r.iloc[:6].tolist(), r.estr) * 100 for _, r in market.iterrows()]
        print(f"€STR-AAA shift at {t:>5} year(s): mean {np.mean(d):+.1f} bp, min {min(d):+.1f}, max {max(d):+.1f}")
    b = [v * 1e4 for m, v in monthly_bases(_market()).items()]
    print(f"monthly EURIBOR 6M - OIS basis: min {min(b):.1f} bp, max {max(b):.1f} bp")


def of_day(quotes: pd.DataFrame, day: date) -> tuple[dict, dict]:
    """(OIS quotes, 6M quotes) of the day, in %, in the format of `risk.build`."""
    g = quotes[quotes.date == day]
    o, s6 = g[g.type == "OIS"], g[g.type.isin(["DEPOSIT", "FRA", "IRS"])]
    return dict(zip(o.tenor, o.rate)), dict(zip(s6.type + " " + s6.tenor, s6.rate))
