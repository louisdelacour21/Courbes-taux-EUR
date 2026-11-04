"""NSS fitted each day to the bootstrapped zeros (Hagan-West): RMSE, parameter stability, extrapolation.

The RMSE only makes sense on noisy quotes: without noise, the quotes derive from a Svensson curve and the fit is
almost perfect by construction (control run one day in ten).

    python studies/nss.py   ->   studies/nss.md, studies/nss_parameters.csv
"""
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ratecurves import dates as dt  # noqa: E402
from ratecurves import quotes as c  # noqa: E402
from ratecurves.curves import CurveHW, estr_curve, euribor6m_curve  # noqa: E402
from ratecurves.nss import fit_curve  # noqa: E402


def curves_of_day(quotes, day):
    ois, six = c.of_day(quotes, day)
    estr = estr_curve(day, ois, CurveHW)
    return {"€STR": estr, "6M": euribor6m_curve(day, six, estr, CurveHW)}


def main():
    noisy = c.read_quotes()
    days = sorted(noisy.date.unique())
    control = set(days[::10])
    clean = c.reconstruct(noise=False)
    rows = []
    for day in days:
        for source, quotes in (("noisy", noisy), ("noiseless", clean)):
            if source == "noiseless" and day not in control:
                continue
            for name, k in curves_of_day(quotes, day).items():
                m = fit_curve(k)
                t = k.t[1:]
                res = (m.zero(t) + k.x / t) * 1e4
                d40 = day + timedelta(days=round(40 * 365.25))
                t40 = dt.year_fraction(day, d40, "ACT/365F")
                d10 = dt.add_months(day, 120)
                t10 = dt.year_fraction(day, d10, "ACT/365F")
                rows.append(dict(date=day, source=source, curve=name, rmse_bp=m.rmse * 1e4,
                                 max_bp=np.abs(res).max(), z10=-k.ln_p(d10) / t10, b0=m.beta[0], b1=m.beta[1], b2=m.beta[2],
                                 b3=m.beta[3], l1=m.l1, l2=m.l2,
                                 extrapolation_40y_bp=(m.zero([t40])[0] + k.ln_p(d40) / t40) * 1e4))
        print(day, flush=True)
    df = pd.DataFrame(rows)
    df[df.source == "noisy"].drop(columns="source").to_csv(Path(__file__).with_name("nss_parameters.csv"),
                                                             index=False, float_format="%.8g")

    md = ["# NSS fitted to the bootstrapped zeros (Hagan-West)", "",
          f"{len(days)} days of noisy quotes; noiseless control one day in ten ({len(control)} days). "
          "Fit to the pillar zeros, equal weights.", "",
          "| Curve | Quotes | Mean RMSE (bp) | Max RMSE (bp) | Max residual (bp) |", "|---|---|---|---|---|"]
    for (name, src), g in df.groupby(["curve", "source"], sort=False):
        md.append(f"| {name} | {src} | {g.rmse_bp.mean():.2f} | {g.rmse_bp.max():.2f} | {g.max_bp.max():.2f} |")

    md += ["", "Day-to-day stability (noisy quotes): standard deviation of daily changes, in bp, "
           "and number of days where a λ moves by more than 50%.", "",
           "| Curve | Δ 10Y zero | Δ β0 (level) | Δ β1 (−slope) | Δ β2 (curvature) | Δ β3 | λ jumps |",
           "|---|---|---|---|---|---|---|"]
    for name, g in df[df.source == "noisy"].groupby("curve", sort=False):
        g = g.sort_values("date")
        sd = lambda s: f"{s.diff().std() * 1e4:.1f}"
        jumps = int(((g.l1.pct_change().abs() > 0.5) | (g.l2.pct_change().abs() > 0.5)).sum())
        md.append(f"| {name} | {sd(g.z10)} | {sd(g.b0)} | {sd(g.b1)} | {sd(g.b2)} | {sd(g.b3)} | {jumps} |")

    e = df[df.source == "noisy"].groupby("curve", sort=False).extrapolation_40y_bp
    md += ["", "Extrapolation at 40 years, NSS minus extended flat forward (bp): "
           + "; ".join(f"{n} mean {s.mean():+.1f}, min {s.min():+.1f}, max {s.max():+.1f}" for n, s in e)]
    Path(__file__).with_suffix(".md").write_bytes(("\n".join(md) + "\n").encode("utf-8"))
    print("\n".join(md))


if __name__ == "__main__":
    main()
