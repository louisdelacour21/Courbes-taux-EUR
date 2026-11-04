"""Leave-one-out: log-linear against Hagan-West, on the noisy quotes (with the 10Y IRS basis jump).

For each day and each inner instrument (neither the first nor the last pillar: that would be extrapolation),
the instrument is removed, the curve rebuilt and the gap between its implied rate and its quote measured, in bp.
The 6M curve is rebuilt on the full €STR curve of the same interpolator.
Roughness: Σ (Δf)² / Δt on monthly continuous 1M forwards up to 30 years (proxy of ∫f'²; infinite for
log-linear in the limit, since its forwards are step functions).

    python studies/leave_one_out.py   ->   studies/leave_one_out.md
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ratecurves import dates as dt  # noqa: E402
from ratecurves import quotes as c  # noqa: E402
from ratecurves.curves import Curve, CurveHW, estr_curve, euribor6m_curve, newton  # noqa: E402

CLASSES = {"log-linear": Curve, "Hagan-West": CurveHW}


def study_days(quotes):
    days = sorted(quotes.date.unique())
    jump = [d for d in days if d >= c.JUMP["start"]][: c.JUMP["days"]]
    return sorted(set(days[::10]) | set(jump)), set(jump)


def loo_errors(day, instruments, q, discount, cls):
    """{tenor: gap in bp} for each inner instrument removed."""
    out = {}
    for k in range(1, len(instruments) - 1):
        rest = instruments[:k] + instruments[k + 1:]
        curve = newton(day, rest, np.delete(q, k), discount, cls)
        i = instruments[k]
        rate = i.rate(curve.P, discount) if discount else i.rate(curve.P)
        out[i.tenor] = (rate - q[k]) * 1e4
    return out


def roughness(curve):
    spot = dt.add_business_days(curve.day, 2)
    d = [dt.add_months(spot, m) for m in range(361)]
    t = [dt.year_fraction(curve.day, x, "ACT/365F") for x in d]
    f = [(curve.ln_p(a) - curve.ln_p(b)) / (tb - ta) for a, b, ta, tb in zip(d, d[1:], t, t[1:])]
    tm = [(a + b) / 2 for a, b in zip(t, t[1:])]
    return sum((f2 - f1) ** 2 / (t2 - t1) for f1, f2, t1, t2 in zip(f, f[1:], tm, tm[1:])) * 1e4  # bp²/year


def main():
    quotes = c.read_quotes()
    days, jump = study_days(quotes)
    rows = []  # (day, curve, class, tenor, bp)
    rough = {(n, k): [] for n in ("€STR", "6M") for k in CLASSES}
    for day in days:
        ois, six = c.of_day(quotes, day)
        for name, cls in CLASSES.items():
            estr = estr_curve(day, ois, cls)
            q = np.array([ois[i.tenor] / 100 for i in estr.instruments])
            for t, e in loo_errors(day, estr.instruments, q, None, cls).items():
                rows.append((day, "€STR", name, t, e))
            c6 = euribor6m_curve(day, six, estr, cls)
            for t, e in loo_errors(day, c6.instruments, np.array(c6.quotes), estr.P, cls).items():
                rows.append((day, "6M", name, t, e))
            rough[("€STR", name)].append(roughness(estr))
            rough[("6M", name)].append(roughness(c6))
        print(day, flush=True)

    def stats(keep):
        e = np.abs([r[4] for r in rows if keep(r)])
        return f"{e.mean():.2f} | {e.max():.2f}"

    md = ["# Leave-one-out: log-linear against Hagan-West", "",
          f"{len(days)} days (one quote day in ten + the {len(jump)} days of the 10Y IRS basis jump), "
          "noisy quotes. Gap |implied rate − quote| of the removed instrument, in bp.", "",
          "| Curve | Interpolation | Mean | Max | Jump: mean | Jump: max | Mean roughness (bp²/year) |",
          "|---|---|---|---|---|---|---|"]
    for n in ("€STR", "6M"):
        for k in CLASSES:
            md.append(f"| {n} | {k} | {stats(lambda r: r[1] == n and r[2] == k)} | "
                      f"{stats(lambda r: r[1] == n and r[2] == k and r[0] in jump)} | {np.mean(rough[(n, k)]):.1f} |")
    md += ["", "Per removed instrument (all days, mean | max):", "",
           "| Curve | Instrument | LL mean | LL max | HW mean | HW max |", "|---|---|---|---|---|---|"]
    for n in ("€STR", "6M"):
        tenors = list(dict.fromkeys(r[3] for r in rows if r[1] == n))
        for t in tenors:
            md.append(f"| {n} | {t} | " + " | ".join(stats(lambda r: r[1] == n and r[2] == k and r[3] == t)
                                                    for k in CLASSES) + " |")
    out = Path(__file__).with_suffix(".md")
    out.write_bytes(("\n".join(md) + "\n").encode("utf-8"))
    print("\n".join(md[:12]))


if __name__ == "__main__":
    main()
